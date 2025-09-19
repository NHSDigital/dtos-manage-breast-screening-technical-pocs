#!/usr/bin/env python3
"""
Azure Relay Gateway Listener
Replaces HTTP polling with real-time Azure Relay communication
"""

import asyncio
import websockets
import json
import os
import urllib.parse
import base64
import hashlib
import hmac
import time
import requests
from typing import Optional

# Configuration
GATEWAY_ID = os.getenv("GATEWAY_ID")
RELAY_NAMESPACE = os.getenv("AZURE_RELAY_NAMESPACE", "graham-relay-test.servicebus.windows.net")
HYBRID_CONNECTION_NAME = os.getenv("AZURE_RELAY_HYBRID_CONNECTION", "graham-relay-test-hc")
KEY_NAME = os.getenv("AZURE_RELAY_KEY_NAME", "RootManageSharedAccessKey")
SHARED_ACCESS_KEY = os.getenv("AZURE_RELAY_SHARED_ACCESS_KEY")
DJANGO_BASE_URL = os.getenv("DJANGO_BASE_URL", "http://localhost:8000")

# Validate required environment variables
if not GATEWAY_ID:
    raise ValueError("GATEWAY_ID environment variable is not set.")

if not SHARED_ACCESS_KEY:
    raise ValueError("AZURE_RELAY_SHARED_ACCESS_KEY environment variable is not set.")

def create_sas_token(service_namespace: str, entity_path: str, sas_key_name: str, sas_key: str, expiry_in_seconds: int = 3600) -> str:
    """Create SAS token for Azure Relay authentication"""
    uri = "http://" + service_namespace + "/" + entity_path
    encoded_resource_uri = urllib.parse.quote_plus(uri)
    expiry = str(int(time.time() + expiry_in_seconds))
    string_to_sign = encoded_resource_uri + '\n' + expiry
    signature = base64.b64encode(
        hmac.new(sas_key.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha256).digest()
    )
    token = f"SharedAccessSignature sr={encoded_resource_uri}&sig={urllib.parse.quote_plus(signature)}&se={expiry}&skn={sas_key_name}"
    return token

async def send_confirmation(message_id: str) -> bool:
    """Send confirmation back to Django app via HTTP"""
    try:
        confirm_url = f"{DJANGO_BASE_URL}/gateway-messages/{GATEWAY_ID}/confirmations"
        confirmation_payload = {"message_id": message_id}

        loop = asyncio.get_event_loop()
        # Use run_in_executor to make the blocking requests call async
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(confirm_url, json=confirmation_payload, timeout=5)
        )
        response.raise_for_status()
        print(f"✅ Confirmed message: {message_id}")
        return True
    except requests.RequestException as e:
        print(f"❌ Failed to confirm message {message_id}: {e}")
        return False

async def process_message(message_data: dict) -> None:
    """Process a received message"""
    message_id = message_data.get("message_id")
    payload = message_data.get("payload")
    destination = message_data.get("destination")

    print(f"📨 Received message: {message_id}")
    print("📤 Sending:")
    print(payload)
    print(f"📍 To: {destination}")

    # In production, this is where you'd send the payload to the actual destination
    # For now, we just simulate processing
    await asyncio.sleep(0.1)  # Simulate processing time

    # Send confirmation back to Django app
    await send_confirmation(message_id)

async def listen_for_messages():
    """Listen for messages from Azure Relay"""
    # Generate SAS token
    token = create_sas_token(RELAY_NAMESPACE, HYBRID_CONNECTION_NAME, KEY_NAME, SHARED_ACCESS_KEY)
    url = f'wss://{RELAY_NAMESPACE}/$hc/{HYBRID_CONNECTION_NAME}?sb-hc-action=listen&sb-hc-token={urllib.parse.quote_plus(token)}'

    print(f"🎧 Gateway {GATEWAY_ID}: Starting Azure Relay listener...")
    print(f"🔗 Connecting to: {HYBRID_CONNECTION_NAME}")

    try:
        async with websockets.connect(url, compression=None) as websocket:
            print("✅ Connected to Azure Relay - waiting for connection requests...")

            async for message in websocket:
                try:
                    # Parse the Azure Relay connection request
                    data = json.loads(message)

                    # Check if this is a connection request from Azure Relay
                    if 'accept' in data:
                        print(f"🔗 Connection request received from Django app")

                        # Extract the accept URL to connect to the sender
                        accept_url = data['accept']['address']
                        connection_id = data['accept']['id']

                        print(f"📞 Accepting connection {connection_id[:8]}...")

                        # Connect to the sender through the accept URL
                        try:
                            async with websockets.connect(accept_url, compression=None) as client_websocket:
                                print("✅ Connected to Django app - waiting for messages...")

                                # Receive the actual message from Django app
                                try:
                                    client_message = await asyncio.wait_for(client_websocket.recv(), timeout=30)
                                    message_data = json.loads(client_message)

                                    # Process the message
                                    await process_message(message_data)

                                    # Send acknowledgment back to Django app
                                    ack_response = {"status": "processed", "message_id": message_data.get("message_id")}
                                    await client_websocket.send(json.dumps(ack_response))

                                except asyncio.TimeoutError:
                                    print("⏰ No message received within timeout")
                                except json.JSONDecodeError as e:
                                    print(f"❌ Failed to parse message: {e}")

                        except Exception as accept_error:
                            print(f"❌ Error accepting connection: {accept_error}")

                    else:
                        print(f"📨 Received other message: {data}")

                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse Azure Relay message: {e}")
                except Exception as e:
                    print(f"❌ Error processing message: {e}")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"🔌 Connection closed: {e}")
    except Exception as e:
        print(f"❌ Connection error: {type(e).__name__}: {e}")

async def main():
    """Main function - run the Azure Relay listener"""
    print("🚀 Azure Relay Gateway Starting...")
    print(f"🆔 Gateway ID: {GATEWAY_ID}")

    while True:
        try:
            await listen_for_messages()
        except KeyboardInterrupt:
            print("\n👋 Shutting down gateway...")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            print("🔄 Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())