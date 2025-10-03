import os
import time
import requests

# Get ID from environment variable
GATEWAY_ID = os.getenv("GATEWAY_ID")

# Validate that ID is present
if not GATEWAY_ID:
    raise ValueError("GATEWAY_ID environment variable is not set.")

# Define endpoints
BASE_URL = f"http://localhost:8000/gateway-messages/{GATEWAY_ID}"
CONFIRM_URL = f"{BASE_URL}/confirmations"

def poll_and_confirm():
    """Polls the remote endpoint and confirms received messages."""
    while True:
        try:
            # Poll the endpoint
            response = requests.get(BASE_URL, timeout=5)
            response.raise_for_status()  # Raise an error for bad responses

            data = response.json()  # Parse JSON response

            if isinstance(data, list):  # Ensure response is a list
                print(f"{len(data)} messages received")
                for message in data:
                    message_id = message.get("message_id")
                    print(f"Received message: {message_id}")
                    if message_id:
                        print("Sending:")
                        print(message.get("payload"))
                        print(f"To: {message.get("destination")}")
                        # Send confirmation
                        confirmation_payload = {
                            "message_id": message_id
                        }
                        confirm_response = requests.post(CONFIRM_URL, json=confirmation_payload, timeout=5)
                        confirm_response.raise_for_status()
                        print(f"Confirmed message: {message_id}")
            else:
                print("Unexpected response format")

        except requests.RequestException as e:
            print(f"Error: {e}")

        time.sleep(1)  # Wait for 1 second before polling again

if __name__ == "__main__":
    poll_and_confirm()
