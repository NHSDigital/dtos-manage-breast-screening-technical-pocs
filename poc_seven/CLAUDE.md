# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**POC Seven: NHS Digital Breast Screening Service - Lightweight Gateway with Local PACS Storage**

This is a proof of concept for a breast screening service that demonstrates bidirectional communication between a cloud-based Django web application and an on-premises DICOM gateway behind a firewall. The key innovation is a lightweight, production-like PACS architecture that stores mammography images locally on the gateway before processing and sending metadata to the cloud.

## Architecture

The system consists of two main components communicating via Azure Relay over HTTPS:

### Cloud Service (`manage_screening/`)
- **Django 5.0** web application with PostgreSQL database
- Manages clinics, appointments, and participants
- Displays real-time image galleries with Server-Sent Events (SSE)
- Sends worklist actions to gateway
- Receives MPPS status updates and image metadata from gateway

### Gateway (`gateway/`)
- **Lightweight Python DICOM services** (no Orthanc dependency)
- Standalone Worklist Server (Port 4243): C-FIND queries, MPPS status tracking
- Standalone PACS Server (Port 4244): C-STORE image storage, C-ECHO verification
- Hash-based file storage (production-like: `15/77/hash.dcm`)
- Separate SQLite databases for worklist and PACS
- Processes images and generates thumbnails for cloud transmission

### Communication Flow
```
Cloud (Django) ──[worklist actions]──> Azure Relay ──> Gateway
Cloud (Django) <──[MPPS + images]──── Azure Relay <── Gateway
```

Azure Relay uses **two bidirectional hybrid connections** (one per direction) to work through firewalls using outbound HTTPS only.

## Common Commands

### Running Services

```bash
# Start cloud service (from manage_screening/)
docker-compose up --build
# Django UI: http://localhost:8000
# Admin: http://localhost:8000/admin/

# Start gateway (from gateway/)
docker-compose up --build
# DICOM Worklist: localhost:4243
# DICOM PACS: localhost:4244
```

### Database Operations

```bash
# Django migrations
docker-compose exec manage-screening python manage.py makemigrations
docker-compose exec manage-screening python manage.py migrate

# Create Django superuser
docker-compose exec manage-screening python manage.py createsuperuser

# Query gateway worklist database
docker exec worklist-server sqlite3 /var/lib/worklist/worklist.db \
  "SELECT accession_number, patient_name, status FROM worklist_items;"

# Query gateway PACS database
docker exec pacs-server sqlite3 /var/lib/pacs/pacs.db \
  "SELECT patient_id, modality, accession_number FROM stored_instances;"

# View stored DICOM files
docker exec pacs-server find /var/lib/pacs/storage -name "*.dcm"
```

### Testing

```bash
# Test worklist server (from gateway/)
uv run python test_worklist.py --mpps

# Test PACS server
uv run python test_pacs.py

# Compile CSS (from manage_screening/)
npm run compile:css
```

### Development

```bash
# View logs
docker-compose logs -f manage-screening
docker-compose logs -f gateway-event-listener
docker-compose logs -f relay-listener
docker-compose logs -f pacs-server

# Restart specific service after code changes
docker-compose restart <service-name>

# Reset databases (WARNING: deletes all data)
docker-compose down -v
docker-compose up --build
```

## Code Architecture

### Django Application Structure

**Apps:**
- `gateway/`: Cloud-gateway communication, Study/Series/Image models
- `provider/`: Clinic/appointment management, appointment state machine
- `participant/`: Patient demographics
- `manage_screening/`: Django project configuration

**Key Models:**
- `Participant`: Patient information
- `Clinic`: Screening clinic with date and provider
- `Appointment`: Patient appointment with state machine
  - States: `checked_in` → `sent_to_modality` → `in_progress` → `complete`/`cancelled`
- `GatewayAction`: Audit trail of actions sent to gateway
- `Study/Series/Image`: DICOM hierarchy with metadata and thumbnails

**Views & Templates:**
- Jinja2 templates in each app's `jinja2/` directory
- NHS Frontend components via `nhsuk-frontend` npm package
- Real-time updates via SSE endpoints (`/api/.../stream`)

### Gateway Architecture

**Python Services:**
- `standalone_worklist_server.py`: DICOM Worklist (C-FIND) + MPPS (N-CREATE/N-SET)
- `pacs_server.py`: DICOM Storage (C-STORE) with 120 SOP class support
- `pacs_storage.py`: Hash-based storage layer with SQLite indexing
- `relay_listener.py`: Receives worklist actions from cloud
- `relay_event_sender.py`: Sends MPPS/image events to cloud
- `image_listener.py`: Polls PACS for new images, generates thumbnails
- `thumbnail_generator.py`: Creates 188px height thumbnails at Q25

**Storage:**
- Worklist: `worklist.db` (SQLite with scheduled procedures)
- PACS: `pacs.db` (SQLite with image metadata)
- DICOM files: Hash-based paths (`storage/15/77/15770826be837125.dcm`)

### Message Flows

**1. Send Appointment to Modality:**
- User clicks "Send to modality" → Django creates `GatewayAction`
- `action_sender.py` sends via Azure Relay
- Gateway `relay_listener.py` receives and creates worklist item
- Modality queries worklist via C-FIND

**2. Image Storage and Processing:**
- Modality sends image via C-STORE to Port 4244
- `pacs_server.py` stores in hash-based directory
- `pacs_storage.py` indexes metadata in SQLite
- `image_listener.py` detects new image (polls every 2s)
- `thumbnail_generator.py` creates thumbnail
- `relay_event_sender.py` sends metadata + thumbnail to cloud
- Django creates Study/Series/Image records
- UI updates via SSE stream

**3. MPPS Status Updates:**
- Modality sends MPPS to Port 4243 (N-CREATE: start, N-SET: complete)
- Gateway updates worklist status and sends event to cloud
- Django updates `Appointment.state`
- UI updates via SSE stream

## Important Patterns

### Appointment State Machine
States flow: `checked_in` → `sent_to_modality` → `in_progress` → `complete`/`cancelled`

The UI adapts based on state:
- Before images: Status in blue inset box with "- Awaiting images" text for `sent_to_modality`/`in_progress`
- After images arrive or status is `complete`: Status tag moves to h1 line next to participant name

### Real-Time Updates
The application uses Server-Sent Events (SSE) for real-time updates:
- Appointment status changes stream to clinic list and detail pages
- New images appear dynamically as they're received
- JavaScript maintains WebSocket connections with auto-reconnect

### Azure Relay Configuration
**Two hybrid connections required** (only one listener allowed per connection):
- Connection 1: Django sends worklist actions → Gateway listens
- Connection 2: Gateway sends MPPS/images → Django listens

Both use outbound HTTPS, no inbound firewall rules needed.

### Hash-Based PACS Storage
Production-like approach for scalability:
- SHA256 hash of SOP Instance UID determines storage path
- Two-level directory structure: `15/77/hash.dcm`
- Even distribution, avoids deep hierarchies
- All metadata indexed in SQLite for fast queries

## Environment Setup

Both `manage_screening/` and `gateway/` need `.env` files. Copy from `.env.development` templates.

**Critical shared variables:**
- `AZURE_RELAY_NAMESPACE`: Azure Service Bus namespace URL
- `AZURE_RELAY_HYBRID_CONNECTION`: Connection name for Django → Gateway
- `AZURE_RELAY_EVENTS_HYBRID_CONNECTION`: Connection name for Gateway → Django
- `AZURE_RELAY_KEY_NAME`: Usually `RootManageSharedAccessKey`
- `AZURE_RELAY_SHARED_ACCESS_KEY`: Shared secret from Azure Portal

See `RELAY_SETUP.md` for detailed Azure Relay configuration.

## Database migrations

This is a proof of concept so no existing data needs to be preserved when making database changes.
They can be made in the init scripts or existing migrations as they are run at the beginning of each demo.

## Seed data
The manage_screening app has a seed command that populates the DB. This is run when the app is started.

## Technology Stack

**Backend:** Python 3.12, Django 5.0, PostgreSQL 15, SQLite 3
**DICOM:** pynetdicom 3.0.4, pydicom 3.0.1, dcmtk
**Communication:** websockets 15.0, Azure Relay, SSE
**Frontend:** Jinja2, NHS Frontend 10.2.2, Sass 1.93.3
**Images:** Pillow 12.0
**Tools:** uv 0.9.7, Docker, gunicorn 22.0

## Key Differences from POC Six

- ❌ Removed Orthanc (heavyweight dependency)
- ✅ Added standalone Python PACS server
- ✅ Added hash-based storage (production-like)
- ✅ Added separate databases for worklist and PACS
- ✅ Added thumbnail generation on gateway
- ✅ Added image metadata synchronization to cloud

## References

- Gateway architecture: `gateway/README.md`
- Azure Relay setup: `RELAY_SETUP.md`
- Django admin: http://localhost:8000/admin/
- DICOM Standard: https://dicom.nema.org/
