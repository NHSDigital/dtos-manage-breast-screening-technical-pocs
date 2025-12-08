#!/usr/bin/env python3
"""
Azure Relay Event Sender for POC Six Gateway

Sends MPPS status updates back to the manage-screening Django app via Azure Relay.
This enables real-time appointment status updates in the clinic UI.
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
import logging
import threading
from typing import Optional, Dict
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration - for sending events TO Django
# Uses a separate hybrid connection from the one used to receive actions FROM Django
# Connection 1: Django sends → Gateway listens (graham-relay-test-hc)
# Connection 2: Gateway sends → Django listens (graham-relay-test-hc-events)
RELAY_NAMESPACE = os.getenv("AZURE_RELAY_NAMESPACE", "graham-relay-test.servicebus.windows.net")
HYBRID_CONNECTION_NAME = os.getenv("AZURE_RELAY_EVENTS_HYBRID_CONNECTION", "graham-relay-test-hc-events")
KEY_NAME = os.getenv("AZURE_RELAY_KEY_NAME", "RootManageSharedAccessKey")
SHARED_ACCESS_KEY = os.getenv("AZURE_RELAY_SHARED_ACCESS_KEY")

if not SHARED_ACCESS_KEY:
    logger.warning("AZURE_RELAY_SHARED_ACCESS_KEY environment variable is not set. Event sending will fail.")


def create_sas_token(namespace: str, entity_path: str, key_name: str, key: str, expiry_seconds: int = 3600) -> str:
    """Create SAS token for Azure Relay authentication."""
    uri = f"http://{namespace}/{entity_path}"
    encoded_uri = urllib.parse.quote_plus(uri)
    expiry = str(int(time.time() + expiry_seconds))
    signature = base64.b64encode(
        hmac.new(key.encode(), f"{encoded_uri}\n{expiry}".encode(), hashlib.sha256).digest()
    )
    return f"SharedAccessSignature sr={encoded_uri}&sig={urllib.parse.quote_plus(signature)}&se={expiry}&skn={key_name}"


class RelayEventSender:
    """
    Sends MPPS status update events to Django via Azure Relay.

    This class handles the async relay connection and message sending.
    It's designed to be called from the synchronous MPPS handlers in worklist_server.py.
    """

    def __init__(self):
        self._connection = None
        self._thread_lock = threading.Lock()  # Use thread lock for connection management
        self._send_lock = None  # Asyncio lock for send operations (created in async context)

    async def _ensure_connection(self):
        """Ensure we have an active relay connection."""
        if not SHARED_ACCESS_KEY:
            raise ValueError("Azure Relay shared access key not configured")

        with self._thread_lock:
            # Check if connection exists and is open
            if self._connection:
                try:
                    # Check connection state more thoroughly
                    if hasattr(self._connection, 'state') and self._connection.state.name == "OPEN":
                        # Verify it's actually usable
                        return self._connection
                except Exception as e:
                    logger.debug(f"Connection check failed: {e}")
                # Connection closed or invalid, clean up
                try:
                    if self._connection:
                        await self._connection.close()
                except Exception:
                    pass
                self._connection = None

            # Create new connection
            token = create_sas_token(
                RELAY_NAMESPACE,
                HYBRID_CONNECTION_NAME,
                KEY_NAME,
                SHARED_ACCESS_KEY
            )

            # Connect action for sender
            url = (
                f"wss://{RELAY_NAMESPACE}/$hc/{HYBRID_CONNECTION_NAME}"
                f"?sb-hc-action=connect&sb-hc-token={urllib.parse.quote_plus(token)}"
            )

            logger.info(f"Connecting to Azure Relay: {HYBRID_CONNECTION_NAME}")
            self._connection = await connect(url, compression=None)
            logger.info("Connected to Azure Relay")

            return self._connection

    async def send_mpps_event(
        self,
        action_id: str,
        accession_number: str,
        status: str,
        mpps_instance_uid: Optional[str] = None
    ) -> bool:
        """
        Send an MPPS status update event to Django.

        Args:
            action_id: The original action_id (source_message_id) from the worklist creation
            accession_number: The accession number for reference
            status: The MPPS status (IN PROGRESS, COMPLETED, DISCONTINUED)
            mpps_instance_uid: Optional MPPS instance UID

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # ALWAYS create a fresh connection for each message
            # Azure Relay rendezvous pattern requires new connection per send
            self._connection = None
            conn = await self._ensure_connection()

            # Build the event payload
            event = {
                "schema_version": 1,
                "event_type": "mpps.status_update",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_system": "gateway-mwl",
                "data": {
                    "action_id": action_id,
                    "accession_number": accession_number,
                    "status": status,
                    "mpps_instance_uid": mpps_instance_uid
                }
            }

            # Send the event
            await conn.send(json.dumps(event))
            logger.info(
                f"Sent MPPS event: action_id={action_id}, "
                f"accession={accession_number}, status={status}"
            )

            # Wait for acknowledgment (with timeout)
            try:
                response = await asyncio.wait_for(conn.recv(), timeout=10)
                response_data = json.loads(response)
                logger.info(f"Received acknowledgment: {response_data}")

                # Close connection after successful send/recv
                await conn.close()
                self._connection = None

                # Check if Django actually succeeded
                status_result = response_data.get("status")
                if status_result in ["updated", "action_not_found", "appointment_not_found"]:
                    # These are all valid responses (action_not_found is expected if action was created before this feature)
                    return True
                else:
                    logger.warning(f"Django reported unexpected status: {status_result}")
                    return status_result not in ["error", "unknown_status"]

            except asyncio.TimeoutError:
                logger.error("Timeout waiting for MPPS acknowledgment - message may not have been delivered")
                self._connection = None
                return False
            except Exception as e:
                logger.error(f"Error receiving MPPS acknowledgment: {e}")
                self._connection = None
                return False

        except Exception as e:
            logger.error(f"Error sending MPPS event: {e}", exc_info=True)
            # Clear connection on error
            self._connection = None
            return False

    async def send_image_event(self, message_dict: Dict) -> bool:
        """
        Send an image_received event to Django.

        Args:
            message_dict: The complete image_received message dictionary

        Returns:
            True if sent successfully, False otherwise
        """
        # Ensure we have an asyncio lock for this event loop
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()

        # Acquire lock to ensure only one send/recv happens at a time
        async with self._send_lock:
            conn = None
            try:
                # ALWAYS create a fresh connection for each message
                # Azure Relay rendezvous pattern requires new connection per send
                self._connection = None
                conn = await self._ensure_connection()

                # Send the event (message_dict already has proper structure)
                await conn.send(json.dumps(message_dict))

                sop_uid = message_dict.get("parameters", {}).get("image", {}).get("sop_instance_uid", "unknown")
                logger.info(f"Sent image event: sop_instance_uid={sop_uid}")

                # Wait for acknowledgment (with timeout)
                try:
                    response = await asyncio.wait_for(conn.recv(), timeout=10)
                    response_data = json.loads(response)
                    logger.info(f"Received acknowledgment: {response_data}")

                    # Close connection after successful send/recv
                    await conn.close()
                    self._connection = None

                    # Check if Django actually succeeded
                    status = response_data.get("status")
                    if status in ["created", "already_exists"]:
                        return True
                    else:
                        logger.error(f"Django reported non-success status: {status}")
                        return False

                except asyncio.TimeoutError:
                    logger.error("Timeout waiting for acknowledgment - message may not have been delivered")
                    self._connection = None
                    return False
                except Exception as e:
                    logger.error(f"Error receiving acknowledgment: {e}")
                    # Clear connection on error so next send will create a new one
                    self._connection = None
                    return False

            except Exception as e:
                logger.error(f"Error sending image event: {e}", exc_info=True)
                # Clear connection on error
                self._connection = None
                return False

    async def close(self):
        """Close the relay connection."""
        if self._connection:
            try:
                await self._connection.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            finally:
                self._connection = None


# Global singleton instance
_event_sender = None


def get_event_sender() -> RelayEventSender:
    """Get the global event sender instance."""
    global _event_sender
    if _event_sender is None:
        _event_sender = RelayEventSender()
    return _event_sender


# Global threading lock for synchronous sends
_sync_send_lock = threading.Lock()


def send_mpps_event_sync(
    action_id: str,
    accession_number: str,
    status: str,
    mpps_instance_uid: Optional[str] = None
) -> bool:
    """
    Synchronous wrapper for sending MPPS events.

    This function can be called from synchronous code (like worklist_server.py).
    It runs the async send synchronously to ensure proper error handling.
    Uses a threading lock to prevent concurrent sends from different threads.

    Args:
        action_id: The original action_id (source_message_id) from the worklist creation
        accession_number: The accession number for reference
        status: The MPPS status (IN PROGRESS, COMPLETED, DISCONTINUED)
        mpps_instance_uid: Optional MPPS instance UID

    Returns:
        True if sent successfully, False otherwise
    """
    with _sync_send_lock:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            sender = get_event_sender()
            result = loop.run_until_complete(
                sender.send_mpps_event(action_id, accession_number, status, mpps_instance_uid)
            )
            return result
        except Exception as e:
            logger.error(f"Error in MPPS event sender: {e}", exc_info=True)
            return False
        finally:
            loop.close()


def send_image_event_sync(message_dict: Dict) -> bool:
    """
    Synchronous wrapper for sending image events.

    This function can be called from synchronous code (like image_listener.py).
    It runs the async send synchronously to ensure proper ordering.
    Uses a threading lock to prevent concurrent sends from different threads.

    Args:
        message_dict: The complete image_received message dictionary

    Returns:
        True if sent successfully, False otherwise
    """
    with _sync_send_lock:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            sender = get_event_sender()
            result = loop.run_until_complete(
                sender.send_image_event(message_dict)
            )
            return result
        except Exception as e:
            logger.error(f"Error in image event sender: {e}", exc_info=True)
            return False
        finally:
            loop.close()
