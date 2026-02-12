#!/usr/bin/env python3
"""
ServiceBusEventListener
Listens for events from gateway via Azure Service Bus.

Events:
- mpps.status_update: Updates Appointment status when procedures start/complete
- study.image_received: Creates Study/Series/Image records when images are stored

Replaces gateway_event_listener.py - uses Service Bus queues instead of Azure Relay.

Usage:
    python gateway/services/service_bus_event_listener.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from manage_screening root
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Setup Django environment if running standalone
if __name__ == "__main__":
    import django
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'manage_screening.settings')
    django.setup()

from azure.servicebus.aio import ServiceBusClient

# Import event processors from the existing gateway_event_listener
from gateway.services.gateway_event_listener import (
    process_mpps_event,
    process_image_received_event,
)

logger = logging.getLogger(__name__)

# Queue for receiving events from gateway
EVENTS_QUEUE = os.getenv("SERVICE_BUS_EVENTS_QUEUE", "poc-gateway-events")


class ServiceBusEventListener:
    """Listens for gateway events from Azure Service Bus queue."""

    def __init__(self):
        self.connection_string = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "")
        self.queue_name = EVENTS_QUEUE

    async def listen(self):
        """Listen for messages from Azure Service Bus."""
        logger.info(f"Connecting to Service Bus queue: {self.queue_name}...")

        async with ServiceBusClient.from_connection_string(self.connection_string) as client:
            async with client.get_queue_receiver(self.queue_name) as receiver:
                logger.info("Connected - waiting for gateway events...")

                async for message in receiver:
                    try:
                        payload = json.loads(str(message))

                        # Route to appropriate handler
                        event_type = payload.get("event_type")
                        message_type = payload.get("message_type")

                        logger.info(f"Received event: {event_type or message_type}")

                        if event_type == "mpps.status_update":
                            result = await process_mpps_event(payload)
                        elif message_type == "study.image_received":
                            result = await process_image_received_event(payload)
                        else:
                            logger.warning(f"Unknown event: {event_type or message_type}")
                            result = {"status": "unknown_event"}

                        logger.info(f"Processed: {result.get('status')}")

                        # Complete or abandon based on result
                        if result.get("status") in ("created", "updated", "already_exists", "unknown_event"):
                            await receiver.complete_message(message)
                        else:
                            await receiver.abandon_message(message)

                    except Exception as e:
                        logger.error(f"Failed to process message: {e}")
                        await receiver.abandon_message(message)


async def main():
    """Main event loop."""
    logger.info("POC Eight Service Bus Event Listener Starting...")

    while True:
        try:
            await ServiceBusEventListener().listen()
        except KeyboardInterrupt:
            logger.info("\nShutting down...")
            break
        except Exception as e:
            logger.error(f"Connection error: {e}")
            logger.info("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())
