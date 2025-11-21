#!/usr/bin/env python3
"""
MPPS Event Listener for Django

Listens for MPPS status update events from gateway via Azure Relay.
Updates Appointment status in real-time when procedures start/complete.

Usage:
    python manage.py run_mpps_listener

Or run directly:
    python gateway/services/mpps_event_listener.py
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
import logging
from typing import Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Setup Django environment if running standalone
if __name__ == "__main__":
    import django
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manage_screening.settings')
    django.setup()

from django.utils import timezone
from gateway.models import GatewayAction
from provider.models import Appointment, AppointmentState

# Azure Relay Configuration - for receiving events FROM gateway
# Uses a separate hybrid connection from the one used to send actions TO gateway
# Connection 1: Django sends → Gateway listens (graham-relay-test-hc)
# Connection 2: Gateway sends → Django listens (graham-relay-test-hc-events)
RELAY_NAMESPACE = os.getenv("AZURE_RELAY_NAMESPACE", "graham-relay-test.servicebus.windows.net")
HYBRID_CONNECTION_NAME = os.getenv("AZURE_RELAY_EVENTS_HYBRID_CONNECTION", "graham-relay-test-hc-events")
KEY_NAME = os.getenv("AZURE_RELAY_KEY_NAME", "RootManageSharedAccessKey")
SHARED_ACCESS_KEY = os.getenv("AZURE_RELAY_SHARED_ACCESS_KEY")

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


# MPPS status to Appointment state mapping
STATUS_MAPPING = {
    'IN PROGRESS': AppointmentState.IN_PROGRESS.value,
    'COMPLETED': AppointmentState.COMPLETE.value,
    'DISCONTINUED': AppointmentState.CANCELLED.value,
}


async def process_mpps_event(payload: dict) -> dict:
    """
    Process an MPPS status update event and update the Appointment.

    Args:
        payload: The event payload from the gateway

    Returns:
        dict with status and action_id
    """
    try:
        event_type = payload.get("event_type")
        data = payload.get("data", {})

        if event_type != "mpps.status_update":
            logger.warning(f"Unknown event type: {event_type}")
            return {"status": "unknown_event"}

        action_id = data.get("action_id")
        accession_number = data.get("accession_number")
        mpps_status = data.get("status")
        mpps_instance_uid = data.get("mpps_instance_uid")

        logger.info(
            f"Received MPPS event: action_id={action_id}, "
            f"accession={accession_number}, status={mpps_status}"
        )

        # Map MPPS status to Appointment state
        appointment_state = STATUS_MAPPING.get(mpps_status)
        if not appointment_state:
            logger.warning(f"Unknown MPPS status: {mpps_status}")
            return {"status": "unknown_status", "action_id": action_id}

        # Look up the GatewayAction by ID (using sync_to_async)
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_action():
            try:
                return GatewayAction.objects.get(id=action_id)
            except GatewayAction.DoesNotExist:
                return None

        action = await get_action()
        if not action:
            logger.error(f"GatewayAction not found: {action_id}")
            return {"status": "action_not_found", "action_id": action_id}

        # Get the appointment_id from the action payload
        source_ref = action.payload.get("source_reference", {})
        appointment_id = source_ref.get("appointment_id")

        if not appointment_id:
            logger.error(f"No appointment_id in action payload: {action_id}")
            return {"status": "no_appointment_id", "action_id": action_id}

        # Update the Appointment (using sync_to_async)
        @sync_to_async
        def update_appointment():
            try:
                appointment = Appointment.objects.get(id=appointment_id)
                old_state = appointment.state
                appointment.state = appointment_state
                appointment.save(update_fields=['state', 'updated_at'])
                return {
                    "status": "updated",
                    "action_id": action_id,
                    "appointment_id": str(appointment_id),
                    "old_state": old_state,
                    "new_state": appointment_state
                }
            except Appointment.DoesNotExist:
                return None

        result = await update_appointment()
        if not result:
            logger.error(f"Appointment not found: {appointment_id}")
            return {"status": "appointment_not_found", "action_id": action_id}

        logger.info(
            f"Updated appointment {appointment_id}: {result['old_state']} -> {result['new_state']}"
        )

        return result

    except Exception as e:
        logger.error(f"Error processing MPPS event: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def listen_for_events():
    """Listen for MPPS events from Azure Relay."""
    token = create_sas_token(RELAY_NAMESPACE, HYBRID_CONNECTION_NAME, KEY_NAME, SHARED_ACCESS_KEY)
    url = f"wss://{RELAY_NAMESPACE}/$hc/{HYBRID_CONNECTION_NAME}?sb-hc-action=listen&sb-hc-token={urllib.parse.quote_plus(token)}"

    logger.info(f"Connecting to Azure Relay: {HYBRID_CONNECTION_NAME}")

    async with connect(url, compression=None) as websocket:
        logger.info("Connected - waiting for MPPS events...")

        async for message in websocket:
            try:
                data = json.loads(message)

                if "accept" in data:
                    accept_url = data["accept"]["address"]
                    logger.info("Incoming MPPS event connection...")

                    async with connect(accept_url, compression=None) as client_ws:
                        client_message = await asyncio.wait_for(client_ws.recv(), timeout=30)
                        payload = json.loads(client_message)

                        # Process the MPPS event
                        response = await process_mpps_event(payload)

                        # Send acknowledgment
                        await client_ws.send(json.dumps(response))
                        logger.info(f"Sent acknowledgment: {response.get('status')}")

            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for message")
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)


async def main():
    """Main event loop."""
    logger.info("POC Six MPPS Event Listener Starting...")

    while True:
        try:
            await listen_for_events()
        except KeyboardInterrupt:
            logger.info("\nShutting down...")
            break
        except Exception as e:
            logger.error(f"Connection error: {e}", exc_info=True)
            logger.info("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
