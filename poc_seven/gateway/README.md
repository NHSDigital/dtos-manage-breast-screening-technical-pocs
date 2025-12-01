# POC Seven: Lightweight Gateway with Local PACS Storage

## Overview

This proof of concept builds on POC Six by removing the Orthanc dependency and implementing a lightweight, production-like PACS architecture on the gateway. The key addition is **local image storage** on the gateway, allowing modalities to store DICOM images which can then be processed and sent back to the cloud service.

**Key technologies:**
- **pynetdicom**: Python library for DICOM networking (standalone servers)
- **pydicom**: Python library for working with DICOM data
- **SQLite**: Separate lightweight databases for worklist and PACS storage
- **Docker**: Containerized deployment with independent services
- **Azure Relay**: Bidirectional communication with cloud service

## What's New in POC Seven

### Removed from POC Six
- ❌ **Orthanc server** - Heavyweight dependency no longer needed

### Added in POC Seven
- ✅ **Standalone PACS Server** - Lightweight Python-based PACS with C-STORE/C-ECHO support
- ✅ **Hash-based Storage** - Production-like file organization using SHA256 hashing
- ✅ **Separate Databases** - Independent SQLite databases for worklist and PACS
- ✅ **Full Metadata Indexing** - Rich database indexing for image queries

### Exploration Plan (POC Seven Focus)

This POC will explore:

1. **Local Image Storage** ✅ COMPLETE
   - Modalities store images to gateway PACS
   - Hash-based storage structure (scalable, production-like)
   - Comprehensive metadata indexing in SQLite

2. **Image Processing Pipeline** 🔄 NEXT
   - Extract metadata from stored DICOM images
   - Generate thumbnails/previews
   - Compress images for cloud transmission

3. **Cloud Synchronization** 📋 PLANNED
   - Send image metadata back to cloud service via Azure Relay
   - Send thumbnails for web UI preview
   - Track synchronization status

4. **Query/Retrieve** 📋 PLANNED
   - Cloud service can request full images when needed
   - Gateway serves images on demand (C-GET/C-MOVE)
   - Bandwidth-aware transmission

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│   Gateway (Docker Compose Network)                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Standalone Worklist Server (Port 4243)              │   │
│  │  - C-FIND (worklist queries)                         │   │
│  │  - N-CREATE/N-SET (MPPS status tracking)             │   │
│  │  - SQLite: worklist.db                               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Standalone PACS Server (Port 4244)                  │   │
│  │  - C-ECHO (verification)                             │   │
│  │  - C-STORE (image storage - 120 SOP classes)         │   │
│  │  - Hash-based storage (15/77/hash.dcm)               │   │
│  │  - SQLite: pacs.db (metadata indexing)               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Azure Relay Listener                                │   │
│  │  - Receives worklist actions from cloud              │   │
│  │  - Sends MPPS status updates to cloud                │   │
│  │  - [Future] Sends image metadata/thumbnails          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
         │ C-FIND/MPPS        │ C-STORE            │ Azure Relay
         │                    │                    │ (HTTPS)
   ┌─────┴─────┐        ┌─────┴─────┐      ┌──────┴───────┐
   │ Modality  │        │ Modality  │      │ Cloud Service│
   │ (MG)      │        │ (MG)      │      │ (Django)     │
   └───────────┘        └───────────┘      └──────────────┘
```

## Components

### 1. Standalone Worklist Server (`scripts/standalone_worklist_server.py`)
Implements DICOM Modality Worklist with MPPS:
- **C-FIND handler**: Responds to worklist queries from modalities
- **N-CREATE handler**: Handles procedure start (status → IN_PROGRESS)
- **N-SET handler**: Handles procedure completion (status → COMPLETED/DISCONTINUED)
- **C-ECHO handler**: DICOM ping for connectivity testing
- **Storage**: `worklist.db` (SQLite with WAL mode)

### 2. Standalone PACS Server (`scripts/pacs_server.py`)
Implements DICOM storage with production-like architecture:
- **C-ECHO handler**: DICOM ping for connectivity testing
- **C-STORE handler**: Receives and stores DICOM images from modalities
- **Supports 120 SOP classes**: All standard storage types (MG, CT, MR, etc.)
- **Hash-based storage**: Files organized by SHA256 hash (e.g., `15/77/hash.dcm`)
- **Database indexing**: Full metadata stored in `pacs.db` for fast queries

### 3. PACS Storage Layer (`scripts/pacs_storage.py`)
Thread-safe storage management:
- **Hash-based path computation**: Two-level directory structure from SHA256 hash
- **Metadata indexing**: Patient, study, series, instance metadata in SQLite
- **File integrity**: SHA256 hashes stored for verification
- **Query methods**: Find by patient, study, accession number, modality, etc.
- **Statistics**: Real-time storage statistics and monitoring

### 4. Database Schemas

**Worklist Database** (`scripts/init_db.sql`):
```sql
CREATE TABLE worklist_items (
    accession_number TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    patient_name TEXT NOT NULL,
    scheduled_date TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    modality TEXT NOT NULL,
    status TEXT DEFAULT 'SCHEDULED',
    source_message_id TEXT,  -- Link to cloud message
    ...
);
```

**PACS Database** (`scripts/init_pacs_db.sql`):
```sql
CREATE TABLE stored_instances (
    sop_instance_uid TEXT PRIMARY KEY,
    storage_path TEXT NOT NULL,        -- Hash-based path
    file_size INTEGER NOT NULL,
    storage_hash TEXT NOT NULL,        -- SHA256 for integrity
    patient_id TEXT,
    study_instance_uid TEXT NOT NULL,
    accession_number TEXT,             -- Cross-reference to worklist
    modality TEXT NOT NULL,
    received_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ...
);
```

### 5. Azure Relay Integration (`scripts/relay_listener.py`)
Bidirectional communication with cloud service:
- **Inbound**: Receives worklist creation requests from cloud
- **Outbound**: Sends MPPS status updates back to cloud
- **Future**: Will send image metadata and thumbnails

## Quick Start

### Build and Run

```bash
cd poc_seven/gateway

# Start all services
docker-compose up --build

# Or start individually
docker-compose up worklist-server
docker-compose up pacs-server
docker-compose up relay-listener
```

### Access Points

- **Worklist Server**: Port 4243 (DICOM)
- **PACS Server**: Port 4244 (DICOM)
- **No web UI** - Lightweight Python services only

## Testing

### Test Worklist Server

```bash
# Install dependencies
uv sync

# Test worklist queries and MPPS
uv run python test_worklist.py

# With MPPS testing
uv run python test_worklist.py --mpps
```

### Test PACS Server

```bash
# Test C-ECHO and C-STORE
uv run python test_pacs.py

# Test only C-ECHO
uv run python test_pacs.py --echo-only

# Test only C-STORE
uv run python test_pacs.py --store-only
```

### Verify Storage Structure

```bash
# View hash-based storage
docker exec pacs-server find /var/lib/pacs/storage -name "*.dcm"

# Query PACS database
docker exec pacs-server sqlite3 /var/lib/pacs/pacs.db \
  "SELECT patient_id, modality, accession_number, storage_path FROM stored_instances;"

# Get storage statistics
docker exec pacs-server sqlite3 /var/lib/pacs/pacs.db \
  "SELECT * FROM study_summary;"
```

## Storage Architecture

### Hash-Based File Organization

Instead of hierarchical Patient/Study/Series structure, files are organized by hash:

```
SOP Instance UID: 1.2.826.0.1.3680043.8.498.97304859...
   ↓ SHA256 hash
Hash: 15770826be837125a1f2c3d4e5f6...
   ↓ Split: first 2 chars / next 2 chars / filename
Storage: 15/77/15770826be837125.dcm
```

**Why hash-based?**
- ✅ Better filesystem performance (avoids deep hierarchies)
- ✅ Scales to millions of studies
- ✅ Even distribution across directories
- ✅ Production PACS systems use similar approaches

### Database Indexing

All metadata stored in SQLite for fast queries:
- Patient demographics
- Study/Series information
- File paths and sizes
- Integrity hashes
- Timestamps
- Cross-references (accession numbers)

## Configuration

### Environment Variables (`.env`)

```bash
# Worklist Server
WORKLIST_AET=SCREENING_MWL
WORKLIST_PORT=4243
WORKLIST_DB_PATH=/var/lib/worklist/worklist.db

# PACS Server
PACS_AET=SCREENING_PACS
PACS_PORT=4244
PACS_STORAGE_PATH=/var/lib/pacs/storage
PACS_DB_PATH=/var/lib/pacs/pacs.db

# Azure Relay
AZURE_RELAY_NAMESPACE=your-namespace.servicebus.windows.net
AZURE_RELAY_HYBRID_CONNECTION=your-connection-name
AZURE_RELAY_SHARED_ACCESS_KEY=your-key

# General
LOG_LEVEL=INFO
```

### Modality Configuration

Configure your mammography modality with:

**Worklist:**
- AE Title: `SCREENING_MWL`
- Host: `<gateway-ip>`
- Port: `4243`

**Storage:**
- AE Title: `SCREENING_PACS`
- Host: `<gateway-ip>`
- Port: `4244`

## Ports

| Port | Service | Protocol | Description |
|------|---------|----------|-------------|
| 4243 | Worklist Server | DICOM | C-FIND (worklist), MPPS |
| 4244 | PACS Server | DICOM | C-ECHO, C-STORE (images) |

## Development

### Modifying Python Scripts

Scripts are mounted as volumes for easier development:

```bash
# Edit any script in ./scripts/
vim scripts/pacs_server.py

# Restart the service
docker-compose restart pacs-server

# Check logs
docker-compose logs -f pacs-server
```

### Database Access

```bash
# Worklist database
docker exec worklist-server sqlite3 /var/lib/worklist/worklist.db

# PACS database
docker exec pacs-server sqlite3 /var/lib/pacs/pacs.db ".schema"
```

### Resetting Databases

```bash
# Remove all volumes and data
docker-compose down -v

# Rebuild and start fresh
docker-compose up --build
```

## Differences from POC Six

| Feature | POC Six | POC Seven |
|---------|---------|-----------|
| Worklist Server | Orthanc Python plugin | Standalone Python service |
| PACS Server | None (Orthanc only) | **NEW: Standalone with hash storage** |
| Storage Structure | N/A | **Hash-based (15/77/hash.dcm)** |
| Databases | 1 (worklist.db) | **2 (worklist.db + pacs.db)** |
| Container Count | 2 (Orthanc + Relay) | 3 (Worklist + PACS + Relay) |
| Dependencies | Orthanc (heavy) | **Pure Python (lightweight)** |
| Image Storage | Not implemented | **Fully implemented** |

## Next Steps (POC Seven Roadmap)

### Phase 1: Local Storage ✅ COMPLETE
- [x] Implement standalone PACS server
- [x] Hash-based file storage
- [x] Database indexing and metadata
- [x] C-STORE from modalities working

### Phase 2: Image Processing 🔄 IN PROGRESS
- [ ] Extract thumbnails from DICOM images
- [ ] Compress images for cloud transmission
- [ ] Generate metadata summaries
- [ ] Handle multi-frame images

### Phase 3: Cloud Synchronization 📋 PLANNED
- [ ] Send image metadata to cloud via Azure Relay
- [ ] Send thumbnails for web preview
- [ ] Track synchronization status in database
- [ ] Handle transmission failures and retries

### Phase 4: Query/Retrieve 📋 PLANNED
- [ ] Cloud service can request full images
- [ ] Implement C-GET/C-MOVE for image retrieval
- [ ] Bandwidth-aware transmission
- [ ] Queue management for large studies

## Troubleshooting

### Container won't start
```bash
docker-compose logs worklist-server
docker-compose logs pacs-server

# Check port availability
lsof -i :4243
lsof -i :4244
```

### No images being stored
```bash
# Check PACS logs
docker-compose logs -f pacs-server

# Verify modality configuration
# Ensure modality is sending to correct AE Title and port
```

### Database queries failing
```bash
# Check database schema
docker exec pacs-server sqlite3 /var/lib/pacs/pacs.db ".schema"

# Verify data exists
docker exec pacs-server sqlite3 /var/lib/pacs/pacs.db \
  "SELECT COUNT(*) FROM stored_instances;"
```

## References

- [pynetdicom Documentation](https://pydicom.github.io/pynetdicom/)
- [DICOM Standard - Worklist (Part 4)](https://dicom.nema.org/medical/dicom/current/output/html/part04.html#chapter_K)
- [DICOM Standard - MPPS (Part 3, Annex B.17)](https://dicom.nema.org/medical/dicom/current/output/html/part03.html#sect_B.17)
- [DICOM Standard - Storage (Part 4)](https://dicom.nema.org/medical/dicom/current/output/html/part04.html#chapter_B)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)

## License

This POC is for demonstration purposes as part of the NHS Digital Breast Screening Service project.
