#!/usr/bin/env python3
"""
Azure Relay Listener for POC Six Gateway
Receives worklist actions from manage-screening and creates MWL items.
"""

import asyncio
from websockets.asyncio.client import connect
import json
import os
import urllib.parse
import base64
import hashlib
import hmac
import time
import sys

# Add scripts directory to path
sys.path.insert(0, "/scripts")
from worklist_storage import WorklistStorage

# Configuration (same relay as poc_five)
RELAY_NAMESPACE = os.getenv("AZURE_RELAY_NAMESPACE", "graham-relay-test.servicebus.windows.net")
HYBRID_CONNECTION_NAME = os.getenv("AZURE_RELAY_HYBRID_CONNECTION", "graham-relay-test-hc")
KEY_NAME = os.getenv("AZURE_RELAY_KEY_NAME", "RootManageSharedAccessKey")
SHARED_ACCESS_KEY = os.getenv("AZURE_RELAY_SHARED_ACCESS_KEY")
DB_PATH = os.getenv("WORKLIST_DB_PATH", "/var/lib/orthanc/worklist/worklist.db")

if not SHARED_ACCESS_KEY:
    raise ValueError("AZURE_RELAY_SHARED_ACCESS_KEY environment variable is not set.")


def create_sas_token(namespace: str, entity_path: str, key_name: str, key: str, expiry_seconds: int = 3600) -> str:
    """Create SAS token for Azure Relay authentication."""
    uri = f"http://{namespace}/{entity_path}"
    encoded_uri = urllib.parse.quote_plus(uri)
    expiry = str(int(time.time() + expiry_seconds))
    signature = base64.b64encode(
        hmac.new(key.encode(), f"{encoded_uri}\n{expiry}".encode(), hashlib.sha256).digest()
    )
    return f"SharedAccessSignature sr={encoded_uri}&sig={urllib.parse.quote_plus(signature)}&se={expiry}&skn={key_name}"


def process_worklist_action(payload: dict, storage: WorklistStorage) -> dict:
    """Process a worklist action and create MWL item."""
    action_type = payload.get("action_type")
    action_id = payload.get("action_id")
    params = payload.get("parameters", {})

    if action_type == "worklist.create_item":
        item = params.get("worklist_item", {})
        participant = item.get("participant", {})
        scheduled = item.get("scheduled", {})
        procedure = item.get("procedure", {})

        storage.add_worklist_item(
            accession_number=item.get("accession_number"),
            patient_id=participant.get("nhs_number"),
            patient_name=participant.get("name"),
            patient_birth_date=participant.get("birth_date"),
            patient_sex=participant.get("sex", ""),
            scheduled_date=scheduled.get("date"),
            scheduled_time=scheduled.get("time"),
            modality=procedure.get("modality"),
            study_description=procedure.get("study_description", ""),
            source_message_id=action_id
        )
        print(f"Created worklist item: {item.get('accession_number')}")
        return {"status": "created", "action_id": action_id}

    else:
        print(f"Unknown action type: {action_type}")
        return {"status": "unknown_action", "action_id": action_id}


async def listen_for_messages(storage: WorklistStorage):
    """Listen for messages from Azure Relay."""
    token = create_sas_token(RELAY_NAMESPACE, HYBRID_CONNECTION_NAME, KEY_NAME, SHARED_ACCESS_KEY)
    url = f"wss://{RELAY_NAMESPACE}/$hc/{HYBRID_CONNECTION_NAME}?sb-hc-action=listen&sb-hc-token={urllib.parse.quote_plus(token)}"

    print(f"Connecting to Azure Relay: {HYBRID_CONNECTION_NAME}")

    async with connect(url, compression=None) as websocket:
        print("Connected - waiting for worklist actions...")

        async for message in websocket:
            try:
                data = json.loads(message)

                if "accept" in data:
                    accept_url = data["accept"]["address"]
                    print("Incoming connection...")

                    async with connect(accept_url, compression=None) as client_ws:
                        client_message = await asyncio.wait_for(client_ws.recv(), timeout=30)
                        payload = json.loads(client_message)

                        # Process the action
                        response = process_worklist_action(payload, storage)

                        # Send acknowledgment
                        await client_ws.send(json.dumps(response))

            except asyncio.TimeoutError:
                print("Timeout waiting for message")
            except Exception as e:
                print(f"Error: {e}")


async def main():
    print("POC Six Relay Listener Starting...")
    storage = WorklistStorage(db_path=DB_PATH)

    while True:
        try:
            await listen_for_messages(storage)
        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            print(f"Connection error: {e}")
            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
