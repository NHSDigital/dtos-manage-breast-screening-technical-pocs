"""
Azure Relay Connection Manager

Manages WebSocket connections to Azure Relay for sending gateway actions.

How it works:
1. Each Gateway has relay configuration (namespace, connection name, key)
2. We create WebSocket connections to Azure Relay using SAS token authentication
3. Messages are sent through the relay to listeners on the gateway side
4. We wait for acknowledgment before marking the action as delivered

The connection flow:
    Django App  --->  Azure Relay  --->  Gateway Listener
                <---  (ack)        <---
"""

import asyncio
from websockets.asyncio.client import connect
import json
import urllib.parse
import base64
import hashlib
import hmac
import time
import os
import logging
from typing import Dict, Optional

from asgiref.sync import sync_to_async


logger = logging.getLogger(__name__)


class RelayConnectionManager:
    """
    Manages Azure Relay connections for sending actions to gateways.

    Maintains a cache of WebSocket connections per gateway to avoid
    reconnecting for every message (connection reuse).
    """

    def __init__(self):
        # Cache of gateway_id -> websocket connection
        self._connections: Dict[str, object] = {}

    def _create_sas_token(
        self,
        namespace: str,
        entity_path: str,
        key_name: str,
        key: str,
        expiry_seconds: int = 3600
    ) -> str:
        """
        Create a Shared Access Signature (SAS) token for Azure Relay authentication.

        Azure Relay requires SAS tokens for authentication. The token contains:
        - sr: The encoded resource URI
        - sig: HMAC-SHA256 signature of (uri + newline + expiry)
        - se: Expiry timestamp
        - skn: The key name (policy name)
        """
        uri = f"http://{namespace}/{entity_path}"
        encoded_uri = urllib.parse.quote_plus(uri)
        expiry = str(int(time.time() + expiry_seconds))

        # Sign: encoded_uri + newline + expiry
        string_to_sign = f"{encoded_uri}\n{expiry}"
        signature = base64.b64encode(
            hmac.new(
                key.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()
        )

        return f"SharedAccessSignature sr={encoded_uri}&sig={urllib.parse.quote_plus(signature)}&se={expiry}&skn={key_name}"

    async def _get_gateway_config(self, gateway_id: str):
        """
        Fetch gateway configuration from the database.

        Uses sync_to_async because Django ORM is synchronous but we're
        in an async context.
        """
        from gateway.models import Gateway

        @sync_to_async
        def get_gateway():
            try:
                return Gateway.objects.get(id=gateway_id)
            except Gateway.DoesNotExist:
                return None

        return await get_gateway()

    async def _create_relay_connection(self, gateway_id: str):
        """
        Create a new WebSocket connection to Azure Relay.

        The URL format for Azure Relay sender connections:
        wss://{namespace}/$hc/{connection_name}?sb-hc-action=connect&sb-hc-token={token}

        Note: 'connect' action is for senders, 'listen' is for receivers.
        """
        gateway = await self._get_gateway_config(gateway_id)
        if not gateway:
            logger.error(f"Gateway {gateway_id} not found")
            return None

        # Get the shared access key from environment variable
        # (we don't store secrets in the database)
        shared_access_key = os.getenv(gateway.relay_shared_access_key_variable_name)
        if not shared_access_key:
            logger.error(
                f"Shared access key not found in env var: "
                f"{gateway.relay_shared_access_key_variable_name}"
            )
            return None

        try:
            token = self._create_sas_token(
                gateway.relay_namespace,
                gateway.relay_hybrid_connection,
                gateway.relay_key_name,
                shared_access_key
            )

            # Build the WebSocket URL for sending
            url = (
                f"wss://{gateway.relay_namespace}/$hc/{gateway.relay_hybrid_connection}"
                f"?sb-hc-action=connect&sb-hc-token={urllib.parse.quote_plus(token)}"
            )

            # Connect with compression disabled (Azure Relay doesn't support it)
            # Use longer timeout for Azure Relay rendezvous pattern
            websocket = await connect(url, compression=None, open_timeout=30)
            logger.info(f"Created relay connection for gateway {gateway_id}")
            return websocket

        except Exception as e:
            logger.error(f"Failed to connect to Azure Relay for gateway {gateway_id}: {e}")
            return None

    async def _get_connection(self, gateway_id: str):
        """
        Get an existing connection or create a new one.

        Implements connection caching - we reuse connections when possible
        to avoid the overhead of reconnecting for every message.
        """
        if gateway_id in self._connections:
            conn = self._connections[gateway_id]
            # Check if still open (websockets 15 uses state attribute)
            try:
                if conn.state.name == "OPEN":
                    return conn
            except Exception:
                pass
            # Connection is closed, remove from cache
            logger.warning(f"Connection to gateway {gateway_id} is closed, reconnecting")
            self._connections.pop(gateway_id, None)

        # Create new connection
        conn = await self._create_relay_connection(gateway_id)
        if conn:
            self._connections[gateway_id] = conn
        return conn

    async def send_action(self, gateway_id: str, action_data: dict) -> dict:
        """
        Send an action to a gateway and wait for acknowledgment.

        Args:
            gateway_id: The gateway's UUID
            action_data: The action payload to send

        Returns:
            dict with 'success' bool and optional 'response' or 'error'
        """
        try:
            conn = await self._get_connection(gateway_id)
            if not conn:
                return {"success": False, "error": "Failed to connect to relay"}

            # Send the action as JSON
            await conn.send(json.dumps(action_data))
            logger.info(f"Sent action {action_data.get('action_id')} to gateway {gateway_id}")

            # Wait for acknowledgment (with timeout)
            try:
                response = await asyncio.wait_for(conn.recv(), timeout=30)
                response_data = json.loads(response)

                if response_data.get("status") in ("created", "processed"):
                    logger.info(
                        f"Action {action_data.get('action_id')} confirmed by gateway"
                    )
                    return {"success": True, "sent": True, "response": response_data}
                else:
                    logger.warning(f"Unexpected response from gateway: {response_data}")
                    return {"success": False, "sent": True, "response": response_data}

            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for acknowledgment from gateway {gateway_id}")
                return {"success": False, "sent": True, "error": "Timeout waiting for acknowledgment"}

        except Exception as e:
            logger.error(f"Error sending action to gateway {gateway_id}: {e}")
            # Remove from cache on error
            self._connections.pop(gateway_id, None)
            return {"success": False, "error": str(e)}

    async def disconnect(self, gateway_id: str):
        """Close connection to a specific gateway."""
        if gateway_id in self._connections:
            try:
                await self._connections[gateway_id].close()
            except Exception as e:
                logger.error(f"Error closing connection to gateway {gateway_id}: {e}")
            finally:
                self._connections.pop(gateway_id, None)


# Global singleton instance
_relay_manager = None


def get_relay_manager() -> RelayConnectionManager:
    """Get the global relay manager instance."""
    global _relay_manager
    if _relay_manager is None:
        _relay_manager = RelayConnectionManager()
    return _relay_manager
