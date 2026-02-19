"""
ServiceBusSender
Sends worklist actions to gateway via Azure Service Bus.

Replaces action_sender.py + relay_manager.py - uses Service Bus queues instead of Azure Relay.

Key differences from relay:
- No background thread needed (send is synchronous and fast)
- No SAS token generation (SDK handles auth)
- No WebSocket connection management
- No acknowledgment wait (Service Bus confirms receipt)
"""

import json
import logging
import os
from pathlib import Path

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from django.utils import timezone
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from gateway.models import GatewayAction

logger = logging.getLogger(__name__)

# Queue for sending commands to gateway
COMMANDS_QUEUE = os.getenv("SERVICE_BUS_COMMANDS_QUEUE", "poc-worklist-commands")


class ServiceBusSender:
    """Sends worklist actions to gateway via Azure Service Bus queue."""

    def __init__(self):
        self.connection_string = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "")
        self.queue_name = COMMANDS_QUEUE

    def send(self, action: GatewayAction) -> bool:
        """Send an action to the worklist-commands queue.

        Args:
            action: The GatewayAction to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            with ServiceBusClient.from_connection_string(self.connection_string) as client:
                with client.get_queue_sender(self.queue_name) as sender:
                    message = ServiceBusMessage(
                        body=json.dumps(action.payload),
                        content_type="application/json",
                        message_id=str(action.id),
                    )
                    sender.send_messages(message)

            # Mark as delivered (Service Bus confirmed receipt)
            action.delivered_at = timezone.now()
            action.save(update_fields=['delivered_at'])
            logger.info(f"Action {action.id} sent to {self.queue_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to send action {action.id}: {e}")
            return False


# Singleton instance
_sender = None


def get_service_bus_sender() -> ServiceBusSender:
    """Get the global sender instance."""
    global _sender
    if _sender is None:
        _sender = ServiceBusSender()
    return _sender


def send_action_to_gateway(action: GatewayAction) -> bool:
    """
    Send a GatewayAction to its gateway via Azure Service Bus.

    This is the main entry point - call this from Django views/services.

    Args:
        action: The GatewayAction instance to send

    Returns:
        bool: True if sent successfully, False otherwise

    Example:
        action = GatewayAction.objects.create(
            gateway=gateway,
            type=GatewayAction.TYPE_WORKLIST_ADD,
            payload=payload_dict
        )
        send_action_to_gateway(action)
    """
    sender = get_service_bus_sender()
    return sender.send(action)
