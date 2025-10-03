"""
Message Sender Service
Handles sending messages to gateways via Azure Relay from Django views
"""

import asyncio
import threading
import logging
from typing import Optional
from gateway.models import Message
from .relay_manager import send_message_to_gateway


logger = logging.getLogger(__name__)


class AsyncMessageSender:
    """Handles async message sending from Django synchronous context"""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._start_event = threading.Event()

    def _run_event_loop(self):
        """Run the event loop in a separate thread"""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._start_event.set()  # Signal that the loop is ready
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Error in async event loop: {e}")
        finally:
            if self._loop:
                self._loop.close()

    def start(self):
        """Start the async event loop in a background thread"""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self._thread.start()
            # Wait for the event loop to be ready
            self._start_event.wait(timeout=5)

    def stop(self):
        """Stop the async event loop"""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def send_message_async(self, message: Message) -> bool:
        """
        Send a message to its gateway asynchronously

        Args:
            message: The Message instance to send

        Returns:
            bool: True if the message was queued for sending, False otherwise
        """
        if not self._loop or self._loop.is_closed():
            self.start()

        if not self._loop:
            logger.error("Failed to start async event loop")
            return False

        try:
            # Schedule the coroutine in the event loop
            future = asyncio.run_coroutine_threadsafe(
                self._send_message_coroutine(message),
                self._loop
            )

            # Don't block - let it run in the background
            # In production, you might want to handle the result via a callback
            logger.info(f"Queued message {message.id} for sending to gateway {message.gateway.id}")
            return True

        except Exception as e:
            logger.error(f"Error queuing message {message.id}: {e}")
            return False

    async def _send_message_coroutine(self, message: Message):
        """Coroutine to send the message via relay"""
        try:
            success = await send_message_to_gateway(
                gateway_id=str(message.gateway.id),
                message_id=str(message.id),
                message_type=message.type,
                payload=message.payload,
                destination=message.destination
            )

            if success:
                # Update the message as delivered
                from django.utils import timezone
                from asgiref.sync import sync_to_async

                # Use sync_to_async to safely update the database from async context
                @sync_to_async
                def update_message():
                    message.delivered_at = timezone.now()
                    message.save(update_fields=['delivered_at'])

                await update_message()
                logger.info(f"Message {message.id} successfully sent and marked as delivered")
            else:
                logger.error(f"Failed to send message {message.id} to gateway {message.gateway.id}")

        except Exception as e:
            logger.error(f"Error in send message coroutine for message {message.id}: {e}")


# Global instance
_message_sender = None


def get_message_sender() -> AsyncMessageSender:
    """Get the global message sender instance"""
    global _message_sender
    if _message_sender is None:
        _message_sender = AsyncMessageSender()
    return _message_sender


def send_message_to_relay(message: Message) -> bool:
    """
    Send a message to its gateway via Azure Relay

    This function can be called from Django views and will handle the message
    sending asynchronously in the background.

    Args:
        message: The Message instance to send

    Returns:
        bool: True if the message was queued for sending, False otherwise
    """
    sender = get_message_sender()
    return sender.send_message_async(message)