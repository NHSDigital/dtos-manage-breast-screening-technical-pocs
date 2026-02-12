"""
ServiceBusEventSender
Sends events (MPPS updates, image received) to manage-screening via Azure Service Bus.

Replaces WebSocket-based event sending with Service Bus queue.
"""

import json
import logging
import os
from pathlib import Path

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# Queue for sending events to manage
EVENTS_QUEUE = os.getenv("SERVICE_BUS_EVENTS_QUEUE", "poc-gateway-events")


class ServiceBusEventSender:
    """Sends events to manage-screening via Azure Service Bus queue."""

    def __init__(self):
        self.connection_string = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "")
        self.queue_name = EVENTS_QUEUE

    def send_event(self, event: dict) -> bool:
        """Send an event to the gateway-events queue.

        Args:
            event: The event payload (dict) to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            with ServiceBusClient.from_connection_string(self.connection_string) as client:
                with client.get_queue_sender(self.queue_name) as sender:
                    message = ServiceBusMessage(
                        body=json.dumps(event),
                        content_type="application/json",
                    )
                    sender.send_messages(message)

            event_type = event.get('event_type') or event.get('message_type')
            logger.info(f"Sent event to {self.queue_name}: {event_type}")
            return True

        except Exception as e:
            logger.error(f"Failed to send event: {e}")
            return False


# Singleton instance
_event_sender = None


def get_event_sender() -> ServiceBusEventSender:
    """Get the global event sender instance."""
    global _event_sender
    if _event_sender is None:
        _event_sender = ServiceBusEventSender()
    return _event_sender


def send_mpps_event(action_id: str, accession_number: str, status: str, mpps_instance_uid: str | None = None) -> bool:
    """
    Send an MPPS status update event to manage-screening.

    Args:
        action_id: The original GatewayAction ID
        accession_number: The accession number
        status: The MPPS status (IN PROGRESS, COMPLETED, DISCONTINUED)
        mpps_instance_uid: The MPPS SOP Instance UID (optional)

    Returns:
        bool: True if sent successfully
    """
    event = {
        "event_type": "mpps.status_update",
        "data": {
            "action_id": action_id,
            "accession_number": accession_number,
            "status": status,
            "mpps_instance_uid": mpps_instance_uid,
        }
    }
    return get_event_sender().send_event(event)


def send_image_received_event(payload: dict) -> bool:
    """
    Send a study.image_received event to manage-screening.

    Args:
        payload: The full image received payload

    Returns:
        bool: True if sent successfully
    """
    return get_event_sender().send_event(payload)


# For testing directly
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Send a test MPPS event
    success = send_mpps_event(
        action_id="test-action-123",
        accession_number="ACC-TEST-001",
        status="IN PROGRESS",
    )
    print(f"Sent test MPPS event: {success}")
