# POC Eight: Azure Service Bus

Proof of concept demonstrating Azure Service Bus as a replacement for Azure Relay for bidirectional communication between the manage app (cloud) and gateway (on-premises).

## What This Proves

- **Manage → Gateway**: Worklist commands sent via Service Bus queue
- **Gateway → Manage**: MPPS status updates and image metadata sent via Service Bus queue
- Messages persist in queues if either side is temporarily offline
- Simpler code than WebSocket-based Azure Relay (no connection management, SAS token generation, or background threads)

## Architecture

```
┌─────────────────────┐                              ┌─────────────────────┐
│   Manage (Django)   │                              │      Gateway        │
│                     │                              │                     │
│  service_bus_sender ├───► poc-worklist-commands ───►  service_bus_       │
│                     │            Queue             │     listener        │
│                     │                              │                     │
│  service_bus_event_ ◄─── poc-gateway-events ◄──────┤  service_bus_event_ │
│     listener        │            Queue             │     sender          │
└─────────────────────┘                              └─────────────────────┘
```

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Azure Service Bus namespace with two queues

## Azure Setup

1. Create a Service Bus namespace in Azure Portal (Standard tier is sufficient)

2. Create two queues:
   - `poc-worklist-commands` (Manage → Gateway)
   - `poc-gateway-events` (Gateway → Manage)

3. Get the connection string:
   - Go to Service Bus namespace → Shared access policies → RootManageSharedAccessKey
   - Copy the Primary Connection String

## Local Setup

### 1. Configure Environment

Copy the template and add your connection string to both `.env` files:

```bash
# Gateway
cd gateway
cp .env.template .env
# Edit .env and set AZURE_SERVICE_BUS_CONNECTION_STRING

# Manage
cd ../manage_screening
cp .env.template .env
# Edit .env and set AZURE_SERVICE_BUS_CONNECTION_STRING
```

**Important**: The connection string contains semicolons. Wrap it in quotes in the .env file:
```
AZURE_SERVICE_BUS_CONNECTION_STRING="Endpoint=sb://your-namespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=your-key"
```

### 2. Install Dependencies

```bash
# Gateway
cd gateway
uv sync

# Manage
cd ../manage_screening
uv sync
```

### 3. Initialize Databases

```bash
cd manage_screening
uv run python manage.py migrate
uv run python manage.py seed
```

## Running the Demo

Open 4 terminal windows:

### Terminal 1: Django Web App
```bash
cd manage_screening
uv run python manage.py runserver
```

### Terminal 2: Gateway Listener (receives worklist commands)
```bash
cd gateway
uv run python src/service_bus_listener.py
```

### Terminal 3: Manage Event Listener (receives images from gateway)
```bash
cd manage_screening
uv run python gateway/services/service_bus_event_listener.py
```

### Terminal 4: Demo Commands
```bash
cd gateway
# After clicking "Send to modality" in the web UI:
uv run python src/demo_send_image.py
```

## Demo Flow

1. Open http://localhost:8000/clinics in your browser
2. Click on today's clinic to see appointments
3. Click **"Send to modality"** for any appointment
   - Watch Terminal 2: Gateway receives the worklist command via Service Bus
   - Status changes to "Sent to modality" (purple tag)
4. In Terminal 4, run `uv run python src/demo_send_image.py`
   - This simulates the gateway receiving DICOM images and sending them to manage
   - Watch Terminal 3: Manage receives 4 image events via Service Bus
5. Click on the appointment name to see the images appear in real-time

## Key Files

### Gateway
- `src/service_bus_listener.py` - Receives worklist commands from manage
- `src/service_bus_event_sender.py` - Sends MPPS/image events to manage
- `src/demo_send_image.py` - Simulates sending mammography images

### Manage (Django)
- `gateway/services/service_bus_sender.py` - Sends worklist commands to gateway
- `gateway/services/service_bus_event_listener.py` - Receives events from gateway
- `gateway/services/gateway_event_listener.py` - Processes received events (updates appointments, creates image records)

## Comparison with Azure Relay

| Aspect | Azure Relay | Azure Service Bus |
|--------|-------------|-------------------|
| Connection | WebSocket (persistent) | AMQP (per-message) |
| Offline handling | Messages lost | Messages queued |
| Code complexity | High (connection management, SAS tokens, background threads) | Low (SDK handles everything) |
| Message size | 64KB | 256KB (Standard) |
| Retry handling | Manual | Built-in (abandon_message) |

## Troubleshooting

**"Connection string is either blank or malformed"**
- Check that the .env file exists and has the connection string
- Ensure the connection string is wrapped in quotes (it contains semicolons)

**"amqp:unauthorized-access"**
- Verify the connection string matches what's in Azure Portal
- Check that the RootManageSharedAccessKey policy has Manage, Send, and Listen permissions

**Images not appearing**
- Make sure the manage event listener (Terminal 3) is running
- Check that you clicked "Send to modality" first (creates the GatewayAction record)
- Verify the gateway listener (Terminal 2) received the worklist command
