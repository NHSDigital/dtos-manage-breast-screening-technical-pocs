"""
Gateway Action Sender

Bridges Django's synchronous views with async WebSocket communication.

The problem:
- Django views run synchronously
- WebSocket communication is async (uses asyncio)
- We can't just call `await` from a Django view

The solution:
- Run an asyncio event loop in a background thread
- Provide a sync function that queues work onto that loop
- The view returns immediately; sending happens in background

Usage:
    from gateway.services.action_sender import send_action_to_relay

    # In your view or service:
    action = GatewayAction.objects.create(...)
    send_action_to_relay(action)  # Non-blocking, returns immediately
"""

import asyncio
import threading
import logging
from typing import Optional

from django.utils import timezone
from asgiref.sync import sync_to_async

from gateway.models import GatewayAction
from .relay_manager import get_relay_manager


logger = logging.getLogger(__name__)


class AsyncActionSender:
    """
    Handles async action sending from Django's synchronous context.

    Creates a background thread with its own event loop to handle
    async WebSocket operations without blocking the Django request.
    """

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._start_event = threading.Event()

    def _run_event_loop(self):
        """
        Run the event loop in a background thread.

        This thread stays alive for the lifetime of the Django process,
        handling all async relay communication.
        """
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
        """Start the background event loop thread."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self._thread.start()
            # Wait for the event loop to be ready (with timeout)
            self._start_event.wait(timeout=5)
            logger.info("Started async action sender background thread")

    def stop(self):
        """Stop the background event loop."""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def send_action_async(self, action: GatewayAction) -> bool:
        """
        Queue an action to be sent via Azure Relay.

        This is non-blocking - it queues the work and returns immediately.
        The actual sending happens in the background thread.

        Args:
            action: The GatewayAction to send

        Returns:
            bool: True if queued successfully, False otherwise
        """
        # Ensure the event loop is running
        if not self._loop or self._loop.is_closed():
            self.start()

        if not self._loop:
            logger.error("Failed to start async event loop")
            return False

        try:
            # Schedule the coroutine in the background event loop
            # This is the key function that bridges sync -> async
            asyncio.run_coroutine_threadsafe(
                self._send_action_coroutine(action),
                self._loop
            )

            logger.info(
                f"Queued action {action.id} for sending to gateway {action.gateway.id}"
            )
            return True

        except Exception as e:
            logger.error(f"Error queuing action {action.id}: {e}")
            return False

    async def _send_action_coroutine(self, action: GatewayAction):
        """
        Coroutine that actually sends the action via relay.

        Runs in the background thread's event loop.
        """
        try:
            manager = get_relay_manager()

            # Build the payload to send
            # The payload is already a dict (stored in JSONField)
            action_data = action.payload

            # Send and wait for acknowledgment
            result = await manager.send_action(
                gateway_id=str(action.gateway.id),
                action_data=action_data
            )

            # Update delivered_at if the message was sent
            if result.get("sent"):
                await self._update_action_delivered(action)

            # Update confirmed_at if we got a successful confirmation response
            if result["success"]:
                response = result.get("response")
                if response and response.get("status") == "created":
                    await self._update_action_confirmed(action)
                    logger.info(f"Action {action.id} successfully sent and confirmed")
                else:
                    logger.info(f"Action {action.id} sent but not confirmed as created")
            else:
                logger.error(
                    f"Failed to send action {action.id}: {result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            logger.error(f"Error in send action coroutine for {action.id}: {e}")

    async def _update_action_delivered(self, action: GatewayAction):
        """
        Update the action's delivered_at timestamp.

        Uses sync_to_async because Django ORM is synchronous.
        """
        @sync_to_async
        def update():
            # Refresh from DB to avoid stale data
            action.refresh_from_db()
            action.delivered_at = timezone.now()
            action.save(update_fields=['delivered_at'])

        await update()

    async def _update_action_confirmed(self, action: GatewayAction):
        """
        Update the action's confirmed_at timestamp.

        Uses sync_to_async because Django ORM is synchronous.
        """
        @sync_to_async
        def update():
            # Refresh from DB to avoid stale data
            action.refresh_from_db()
            action.confirmed_at = timezone.now()
            action.save(update_fields=['confirmed_at'])

        await update()


# Global singleton instance
_action_sender = None


def get_action_sender() -> AsyncActionSender:
    """Get the global action sender instance."""
    global _action_sender
    if _action_sender is None:
        _action_sender = AsyncActionSender()
    return _action_sender


def send_action_to_relay(action: GatewayAction) -> bool:
    """
    Send a GatewayAction to its gateway via Azure Relay.

    This is the main entry point - call this from Django views/services.
    It's non-blocking; the action is queued and sent in the background.

    Args:
        action: The GatewayAction instance to send

    Returns:
        bool: True if queued successfully, False otherwise

    Example:
        action = GatewayAction.objects.create(
            gateway=gateway,
            type=GatewayAction.TYPE_WORKLIST_ADD,
            payload=payload_dict
        )
        send_action_to_relay(action)
    """
    sender = get_action_sender()
    return sender.send_action_async(action)
