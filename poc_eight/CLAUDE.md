# POC Eight: Azure Service Bus

## Goal

Prove that Azure Service Bus can replace Azure Relay for bidirectional communication between the manage app (cloud) and the gateway (on-premises).

## Status: Complete

The POC successfully demonstrates:
- Manage → Gateway: Worklist commands via `poc-worklist-commands` queue
- Gateway → Manage: Image events via `poc-gateway-events` queue
- Real-time UI updates via SSE when images arrive

## Architecture

```
Manage ──[send]──> Queue: poc-worklist-commands ──[receive]──> Gateway
Manage <──[receive]── Queue: poc-gateway-events <──[send]── Gateway
```

## Structure

```
poc_eight/
├── README.md                          # Setup and demo instructions
├── CLAUDE.md
├── gateway/
│   ├── .env.template
│   ├── pyproject.toml
│   └── src/
│       ├── service_bus_listener.py    # Receives worklist commands
│       ├── service_bus_event_sender.py # Sends image events
│       ├── demo_send_image.py         # Demo: simulate sending 4 mammogram images
│       └── services/
│           ├── storage.py             # SQLite worklist storage
│           └── mwl/
│               └── create_worklist_item.py
│
└── manage_screening/                  # Django app
    ├── .env.template
    ├── pyproject.toml
    ├── gateway/services/
    │   ├── service_bus_sender.py          # Sends worklist commands
    │   ├── service_bus_event_listener.py  # Receives image events
    │   └── gateway_event_listener.py      # Processes events (creates Image records)
    └── provider/jinja2/clinic/            # Simplified templates for demo
```

## Running the Demo

See README.md for full instructions. Quick start:

```bash
# Terminal 1: Django
cd manage_screening && uv run python manage.py runserver

# Terminal 2: Gateway listener
cd gateway && uv run python src/service_bus_listener.py

# Terminal 3: Manage event listener
cd manage_screening && uv run python gateway/services/service_bus_event_listener.py

# Terminal 4: After clicking "Send to modality" in browser
cd gateway && uv run python src/demo_send_image.py
```

## Key Learnings

1. **Simpler than Relay**: No WebSocket connection management, SAS token generation, or background threads
2. **Offline resilience**: Messages queue up if receiver is down
3. **python-dotenv quirk**: Connection strings with semicolons need quotes in .env files
4. **Same message formats**: Existing payload structures work unchanged
