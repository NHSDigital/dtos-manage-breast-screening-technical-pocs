# Azure Relay Setup for POC Six

POC Six uses **bidirectional communication** via Azure Relay with **two separate hybrid connections**.

## Architecture

```
┌─────────────────────┐                           ┌──────────────────────┐
│   Django (Manage)   │                           │  Gateway (Behind FW) │
└─────────────────────┘                           └──────────────────────┘
         │                                                          │
         │ (1) Send Worklist Actions                                │
         │ ────────────────────────────────>                        │
         │   Connection: name-of-your-choice-relay-test-hc          │
         │   Django: SENDER                                         │
         │   Gateway: LISTENER (relay-listener)                     │
         │                                                          │
         │                                                          │
         │ (2) Receive MPPS Status Updates                          │
         │ <────────────────────────────────                        │
         │   Connection: name-of-your-choice-relay-test-hc-events   │
         │   Django: LISTENER (mpps-event-listener)                 │
         │   Gateway: SENDER (relay-event-sender)                   │
         │                                                          │
```

## Why Two Connections?

Azure Relay allows **only one listener per hybrid connection** at a time. Since we need bidirectional communication:

- **Connection 1** (`name-of-your-choice-relay-test-hc`): Django sends → Gateway listens
- **Connection 2** (`name-of-your-choice-relay-test-hc-events`): Gateway sends → Django listens

## Firewall Compatibility

Both connections work through firewalls because:

- All communication uses **outbound HTTPS (port 443)**
- "Listening" means maintaining a persistent outbound WebSocket connection
- Azure Relay pushes messages down existing connections
- **No inbound ports required on the gateway!**

## Setup Instructions

### 1. Create Azure Relay Resources

In Azure Portal:

1. Create an Azure Relay namespace (if not exists):
   - Name: `manbrs-gateway-dev`
   - Region: UK South

2. Create **two** Hybrid Connections:
   - Connection 1: `name-of-your-choice-relay-test-hc` (for worklist actions)
   - Connection 2: `name-of-your-choice-relay-test-hc-events` (for MPPS events)

3. Get the Shared Access Policy:
   - Policy Name: `RootManageSharedAccessKey` (default)
   - Copy the Primary Key

### 2. Copy environment variables from .env.development to .env

#### Gateway (.env or .env.development)

```bash
AZURE_RELAY_NAMESPACE=manbrs-gateway-dev.servicebus.windows.net
AZURE_RELAY_HYBRID_CONNECTION=name-of-your-choice-relay-test-hc
AZURE_RELAY_EVENTS_HYBRID_CONNECTION=name-of-your-choice-relay-test-hc-events
AZURE_RELAY_KEY_NAME=RootManageSharedAccessKey
AZURE_RELAY_SHARED_ACCESS_KEY=your_actual_key_here
```

#### Django Manage (.env)

```bash
AZURE_RELAY_NAMESPACE=manbrs-gateway-dev.servicebus.windows.net
AZURE_RELAY_HYBRID_CONNECTION=name-of-your-choice-relay-test-hc
AZURE_RELAY_EVENTS_HYBRID_CONNECTION=name-of-your-choice-relay-test-hc-events
AZURE_RELAY_KEY_NAME=RootManageSharedAccessKey
AZURE_RELAY_SHARED_ACCESS_KEY=your_actual_key_here
```

### 3. Running the Services

#### Gateway

```bash
cd poc_six/gateway
docker-compose up --build
```

This starts:

- Orthanc MWL server
- relay-listener (listens on name-of-your-choice-relay-test-hc)
- Sends MPPS events via relay-event-sender (to name-of-your-choice-relay-test-hc-events)

#### Django

```bash
cd poc_six/manage_screening
docker-compose up --build
```

This starts:

- Django web app (sends to name-of-your-choice-relay-test-hc)
- mpps-event-listener (listens on name-of-your-choice-relay-test-hc-events)

## Message Flows

### Worklist Creation (Django → Gateway)

1. User clicks "Send to Modality" in clinic UI
2. Django creates `GatewayAction` with payload
3. `action_sender.py` sends via relay (as sender) to `name-of-your-choice-relay-test-hc`
4. Gateway `relay-listener.py` receives (as listener)
5. Gateway creates worklist item in SQLite
6. Gateway sends acknowledgment back

### MPPS Status Update (Gateway → Django)

1. Modality sends MPPS (N-CREATE or N-SET) to gateway
2. Gateway `worklist_server.py` receives MPPS
3. Gateway updates worklist item status in SQLite
4. Gateway `relay_event_sender.py` sends event (as sender) to `name-of-your-choice-relay-test-hc-events`
5. Django `mpps_event_listener.py` receives (as listener)
6. Django looks up `GatewayAction` by action_id
7. Django updates `Appointment.state`
8. Clinic UI shows updated status

## Status Mappings

| MPPS Status    | Appointment State | Description                    |
|----------------|-------------------|--------------------------------|
| IN PROGRESS    | in_progress       | Procedure started              |
| COMPLETED      | complete          | Procedure completed            |
| DISCONTINUED   | cancelled         | Procedure discontinued/stopped |

## Troubleshooting

### Django listener shows 401 errors

- Check that `name-of-your-choice-relay-test-hc-events` exists in Azure
- Verify SHARED_ACCESS_KEY is correct
- Ensure only ONE listener per connection

### Gateway can't send events

- Check AZURE_RELAY_EVENTS_HYBRID_CONNECTION is set
- Verify connection exists in Azure
- Check logs: `docker logs orthanc-mwl -f`

### No MPPS updates reaching Django

- Verify both listener containers are running:
  - `docker ps | grep relay`
- Check listener logs:
  - Gateway: `docker logs relay-listener -f`
  - Django: `docker logs mpps_event_listener -f`
- Simulate MPPS from modality to test

## Testing

1. Start both gateway and Django services
2. Open clinic UI and send appointment to modality
3. Simulate MPPS from modality (or use test tool)
4. Check appointment status updates in clinic UI
5. Monitor logs to trace message flow

## Cost Considerations

Azure Relay pricing (Standard tier):

- ~$0.01 per 10,000 messages
- ~$0.01 per relay hour
- For POC with minimal traffic: ~$1-5/month
