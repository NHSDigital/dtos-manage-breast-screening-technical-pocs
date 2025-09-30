"""
Azure Relay Connection Manager
Manages persistent websocket connections to Azure Relay for multiple gateways
"""

import asyncio
import websockets
import json
import urllib.parse
import base64
import hashlib
import hmac
import time
import os
import logging
from typing import Dict, Optional
from django.conf import settings
from asgiref.sync import sync_to_async


logger = logging.getLogger(__name__)


class RelayConnectionManager:
    """Manages Azure Relay connections for multiple gateways"""

    def __init__(self):
        self._connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self._connection_tasks: Dict[str, asyncio.Task] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _create_sas_token(self, service_namespace: str, entity_path: str,
                         sas_key_name: str, sas_key: str, expiry_in_seconds: int = 3600) -> str:
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

    async def _get_gateway_config(self, gateway_id: str):
        """Get gateway configuration from database"""
        # Import here to avoid circular imports
        from gateway.models import Gateway

        # Use sync_to_async for database query
        @sync_to_async
        def get_gateway():
            try:
                return Gateway.objects.get(id=gateway_id)
            except Gateway.DoesNotExist:
                return None

        return await get_gateway()

    async def _update_message_confirmed(self, message_id: str):
        """Update the message confirmed_at field in the database"""
        from gateway.models import Message
        from django.utils import timezone

        @sync_to_async
        def update_message():
            try:
                message = Message.objects.get(id=message_id)
                message.confirmed_at = timezone.now()
                message.save(update_fields=['confirmed_at'])
                logger.info(f"Updated confirmed_at for message {message_id}")
                return True
            except Message.DoesNotExist:
                logger.error(f"Message {message_id} not found for confirmation update")
                return False
            except Exception as e:
                logger.error(f"Error updating confirmed_at for message {message_id}: {e}")
                return False

        await update_message()

    async def _create_relay_connection(self, gateway_id: str):
        """Create a new connection to Azure Relay for sending a message"""
        gateway = await self._get_gateway_config(gateway_id)
        if not gateway:
            logger.error(f"Gateway {gateway_id} not found")
            return None

        # Get the shared access key from environment variable
        shared_access_key = os.getenv(gateway.relay_shared_access_key_variable_name)
        if not shared_access_key:
            logger.error(f"Shared access key not found in environment variable: {gateway.relay_shared_access_key_variable_name}")
            return None

        try:
            # Generate SAS token
            token = self._create_sas_token(
                gateway.relay_namespace,
                gateway.relay_hybrid_connection,
                gateway.relay_key_name,
                shared_access_key
            )

            # Create WebSocket URL for sending messages
            url = f'wss://{gateway.relay_namespace}/$hc/{gateway.relay_hybrid_connection}?sb-hc-action=connect&sb-hc-token={urllib.parse.quote_plus(token)}'

            # Connect to Azure Relay
            websocket = await websockets.connect(url, compression=None)
            logger.info(f"Created new relay connection for gateway {gateway_id}")
            return websocket

        except Exception as e:
            logger.error(f"Failed to connect to Azure Relay for gateway {gateway_id}: {e}")
            return None

    async def _get_relay_connection(self, gateway_id: str) -> Optional[websockets.WebSocketServerProtocol]:
        """Get or create a persistent connection to the Azure Relay for a specific gateway"""
        # Check if we already have a connection
        if gateway_id in self._connections:
            connection = self._connections[gateway_id]
            # Verify the connection is still open
            if not connection.closed:
                return connection
            else:
                logger.warning(f"Connection to gateway {gateway_id} is closed, removing from cache")
                self._connections.pop(gateway_id, None)

        # Create a new connection
        connection = await self._create_relay_connection(gateway_id)
        if connection:
            self._connections[gateway_id] = connection
            logger.info(f"Cached new connection for gateway {gateway_id}")

        return connection

    async def send_message(self, gateway_id: str, message_data: dict) -> bool:
        """Send a message to a specific gateway via Azure Relay"""
        try:
            # Get or create persistent connection
            connection = await self._get_relay_connection(gateway_id)
            if not connection:
                logger.error(f"Failed to get connection for gateway {gateway_id}")
                return False

            # Send the message
            message_json = json.dumps(message_data)
            await connection.send(message_json)
            logger.info(f"Sent message {message_data.get('message_id')} to gateway {gateway_id}")

            # Wait for acknowledgment (with timeout)
            try:
                response = await asyncio.wait_for(connection.recv(), timeout=30)
                response_data = json.loads(response)

                if response_data.get("status") == "processed":
                    logger.info(f"Message {message_data.get('message_id')} successfully processed by gateway {gateway_id}")

                    # Update the message confirmed_at field
                    await self._update_message_confirmed(message_data.get('message_id'))

                    return True
                else:
                    logger.warning(f"Unexpected response from gateway {gateway_id}: {response_data}")
                    return False

            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for acknowledgment from gateway {gateway_id}")
                return False
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse response from gateway {gateway_id}: {e}")
                return False

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Connection to gateway {gateway_id} was closed: {e}, removing from cache")
            self._connections.pop(gateway_id, None)
            return False
        except Exception as e:
            logger.error(f"Error sending message to gateway {gateway_id}: {e}")
            return False

    async def disconnect_gateway(self, gateway_id: str):
        """Disconnect from a specific gateway"""
        if gateway_id in self._connections:
            try:
                await self._connections[gateway_id].close()
            except Exception as e:
                logger.error(f"Error closing connection to gateway {gateway_id}: {e}")
            finally:
                self._connections.pop(gateway_id, None)

    async def disconnect_all(self):
        """Disconnect from all gateways"""
        for gateway_id in list(self._connections.keys()):
            await self.disconnect_gateway(gateway_id)

    def get_connection_count(self) -> int:
        """Get the number of active connections"""
        return len(self._connections)


# Global instance
_relay_manager = None


def get_relay_manager() -> RelayConnectionManager:
    """Get the global relay manager instance"""
    global _relay_manager
    if _relay_manager is None:
        _relay_manager = RelayConnectionManager()
    return _relay_manager


async def send_message_to_gateway(gateway_id: str, message_id: str, message_type: str,
                                 payload: str, destination: str) -> bool:
    """
    Send a message to a gateway via Azure Relay

    Args:
        gateway_id: UUID of the gateway
        message_id: UUID of the message
        message_type: Type of the message (e.g., 'FHIR')
        payload: JSON payload to send
        destination: Destination URL

    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    message_data = {
        "message_id": str(message_id),
        "type": message_type,
        "payload": payload,
        "destination": destination
    }

    manager = get_relay_manager()
    return await manager.send_message(str(gateway_id), message_data)