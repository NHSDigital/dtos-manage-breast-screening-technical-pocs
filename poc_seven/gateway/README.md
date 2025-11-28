# POC Six: Orthanc-based Modality Worklist Server

## Overview

This proof of concept demonstrates running a DICOM Modality Worklist (MWL) server with Modality Performed Procedure Step (MPPS) support on a gateway using Orthanc and Python. The implementation uses:

- **Orthanc**: Open-source DICOM server (provides plugin infrastructure)
- **pynetdicom**: Python library for DICOM networking
- **pydicom**: Python library for working with DICOM data
- **SQLite**: Lightweight database for worklist storage
- **Docker**: Containerized deployment

## Architecture

```
┌─────────────────────────────────────────────────┐
│   Orthanc Container (Gateway)                   │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Orthanc Core                            │  │
│  │  - Web UI (port 8042)                    │  │
│  │  - REST API                              │  │
│  │  - DICOM SCP (port 4242)                 │  │
│  │  - Python plugin loader                  │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Python MWL/MPPS Server                  │  │
│  │  (worklist_server.py)                    │  │
│  │                                          │  │
│  │  - MWL Server (port 4243)                │  │
│  │  - C-FIND handler (worklist queries)     │  │
│  │  - N-CREATE handler (MPPS start)         │  │
│  │  - N-SET handler (MPPS complete)         │  │
│  │  - C-ECHO handler (verification)         │  │
│  └──────────────────────────────────────────┘  │
│                 ▲             │                 │
│                 │             ▼                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Storage Layer (worklist_storage.py)     │  │
│  │  - Thread-safe SQLite access             │  │
│  │  - WAL mode for concurrency              │  │
│  └──────────────────────────────────────────┘  │
│                 │                               │
│                 ▼                               │
│  ┌──────────────────────────────────────────┐  │
│  │  SQLite Database (worklist.db)           │  │
│  │  - Worklist items                        │  │
│  │  - Status tracking (MPPS)                │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
           ▲                    ▲
           │                    │
           │ DICOM C-FIND       │ DICOM MPPS
           │ (Worklist query)   │ (N-CREATE/N-SET)
           │                    │
    ┌──────┴────────┐    ┌──────┴────────┐
    │  Mammography  │    │  Mammography  │
    │  Modality     │    │  Modality     │
    └───────────────┘    └───────────────┘
```

## Components

### 1. Orthanc Configuration (`orthanc.json`)
- Configures Orthanc server with HTTP (8042) and DICOM (4242) ports
- Enables Python plugin from `/usr/share/orthanc/plugins-available/libOrthancPython.so`
- Sets custom MWL AET (`ORTHANC_MWL`) and port (4243)

### 2. Python Worklist Server (`scripts/worklist_server.py`)
Implements:
- **C-FIND handler**: Responds to worklist queries from modalities, reading from SQLite database
- **N-CREATE handler**: Handles procedure start notifications (MPPS), updates database status to `IN_PROGRESS`
- **N-SET handler**: Handles procedure completion/discontinuation (MPPS), updates database status to `COMPLETED`/`DISCONTINUED`
- **C-ECHO handler**: Responds to DICOM ping requests

### 3. Storage Layer (`scripts/worklist_storage.py`)
Thread-safe SQLite interface providing:
- **`find_worklist_items()`**: Query worklist items by modality, date, patient ID, and status
- **`add_worklist_item()`**: Create new worklist entries (for relay listener integration)
- **`update_status()`**: Update procedure status during MPPS workflow
- **`get_statistics()`**: Get counts by status for monitoring
- **WAL mode**: Write-Ahead Logging for concurrent reads/writes without blocking

### 4. Database Schema (`scripts/init_db.sql`)
SQLite database with:
- **`worklist_items` table**: Stores patient demographics, scheduling info, procedure details, status tracking
- **Indexes**: Optimized for common queries (date/modality, status, patient lookups)
- **Sample data**: 3 test worklist items for today
- **Automatic initialization**: Created on first container startup via entrypoint script

### 5. Docker Configuration
- **Dockerfile**: Builds container with Orthanc, Python dependencies, and SQLite
- **docker-compose.yml**: Orchestrates deployment with persistent volumes for database and logs
- **docker-entrypoint.sh**: Initializes SQLite database before starting Orthanc

## Quick Start

### Build and Run

```bash
cd poc_six

# Build and start the container
docker-compose up --build -d

# View logs
docker-compose logs -f
```

On first startup, you'll see:
```
📊 Database not found. Initializing worklist database...
✅ Database initialized successfully
📈 Worklist statistics:
SCHEDULED|3
```

### Access Points

- **Orthanc Web UI**: http://localhost:8042
- **Orthanc REST API**: http://localhost:8042/app/explorer.html
- **DICOM (Orthanc)**: Port 4242
- **DICOM (Worklist/MPPS)**: Port 4243

## Testing the Worklist Server

### 1. Test with Python Test Script (Recommended)

The repository includes a comprehensive test script:

```bash
# Install dependencies with uv
uv sync

# Run basic tests (Echo + Worklist query)
uv run python test_worklist.py

# Test with custom modality
uv run python test_worklist.py -m MG

# Test with specific date
uv run python test_worklist.py -d 20250314

# Include MPPS testing
uv run python test_worklist.py --mpps

# Verbose output
uv run python test_worklist.py -v

# Test remote server
uv run python test_worklist.py -H 192.168.1.100 -p 4243 -a CUSTOM_AET
```

### 2. Test with DICOM Query Tool

Using `findscu` from DCMTK toolkit:

```bash
# Query for worklist items (Mammography modality, today's date)
findscu -v -S -k QueryRetrieveLevel=WORKLIST \
  -k ScheduledProcedureStepSequence[0].Modality=MG \
  -k ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate=$(date +%Y%m%d) \
  localhost 4243 -aec ORTHANC_MWL
```

### 3. Test with Python Script

For custom testing, you can write your own Python scripts:

```python
from pynetdicom import AE
from pynetdicom.sop_class import ModalityWorklistInformationFind
from pydicom.dataset import Dataset

# Create application entity
ae = AE(ae_title='TEST_SCU')
ae.add_requested_context(ModalityWorklistInformationFind)

# Build C-FIND query
ds = Dataset()
ds.PatientName = '*'
ds.PatientID = '*'
ds.ScheduledProcedureStepSequence = [Dataset()]
ds.ScheduledProcedureStepSequence[0].Modality = 'MG'
ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate = ''

# Send query
assoc = ae.associate('localhost', 4243, ae_title='ORTHANC_MWL')
if assoc.is_established:
    responses = assoc.send_c_find(ds, ModalityWorklistInformationFind)
    for (status, identifier) in responses:
        if status and status.Status == 0xFF00:  # Pending
            print(f"Found: {identifier.PatientName}")
    assoc.release()
```

### 4. Test DICOM Echo

```bash
# Test connectivity
echoscu localhost 4243 -aec ORTHANC_MWL
```

## Sample Worklist Data

The database is initialized with 3 sample worklist items (see `scripts/init_db.sql`):

| Accession | Patient ID | Patient Name | Birth Date | Sex | Scheduled Date | Time  | Study Description      |
|-----------|------------|--------------|------------|-----|----------------|-------|------------------------|
| ACC000    | BS000001   | SMITH^JOHN   | 1965-03-15 | M   | Today          | 10:00 | Bilateral Mammography  |
| ACC001    | BS001234   | SMITH^JANE   | 1965-03-15 | F   | Today          | 10:00 | Bilateral Mammography  |
| ACC002    | BS005678   | JONES^MARY   | 1970-08-22 | F   | Today          | 11:00 | Screening Mammography  |

## Managing Worklist Items

### Add Worklist Items via SQLite Command

The simplest way to add worklist items:

```bash
docker-compose exec orthanc-mwl sqlite3 /var/lib/orthanc/worklist.db \
  "INSERT INTO worklist_items (
    accession_number, patient_id, patient_name, patient_birth_date,
    patient_sex, scheduled_date, scheduled_time, modality,
    study_description, procedure_code
  ) VALUES (
    'ACC123', 'BS123456', 'SMITH^JOHN', '19800101',
    'M', strftime('%Y%m%d', 'now'), '143000', 'MG',
    'Screening Mammography', 'MAMMO_SCREENING'
  );"
```

### View Database Contents

```bash
# View all worklist items
docker-compose exec orthanc-mwl sqlite3 /var/lib/orthanc/worklist.db \
  "SELECT accession_number, patient_name, scheduled_time, status FROM worklist_items;"

# Get statistics by status
docker-compose exec orthanc-mwl sqlite3 /var/lib/orthanc/worklist.db \
  "SELECT status, COUNT(*) FROM worklist_items GROUP BY status;"

# View items for specific date
docker-compose exec orthanc-mwl sqlite3 /var/lib/orthanc/worklist.db \
  "SELECT * FROM worklist_items WHERE scheduled_date = '20251117';"
```

### Using Python WorklistStorage Class

For programmatic access (e.g., from relay listener):

```python
from worklist_storage import WorklistStorage

# Initialize storage
storage = WorklistStorage(db_path="/var/lib/orthanc/worklist.db")

# Add a worklist item
storage.add_worklist_item(
    accession_number="ACC123",
    patient_id="BS123456",
    patient_name="SMITH^JOHN",
    patient_birth_date="19800101",
    scheduled_date="20251118",
    scheduled_time="143000",
    modality="MG",
    study_description="Screening Mammography",
    patient_sex="M",
    procedure_code="MAMMO_SCREENING",
    source_message_id="relay_msg_789"  # Optional: link to relay message
)

# Query worklist items
items = storage.find_worklist_items(modality="MG", scheduled_date="20251118")

# Update status (automatically done by MPPS handlers)
storage.update_status("ACC123", "IN_PROGRESS", mpps_instance_uid="1.2.3.4.5")

# Get statistics
stats = storage.get_statistics()
print(f"Scheduled: {stats.get('SCHEDULED', 0)}")
print(f"In Progress: {stats.get('IN_PROGRESS', 0)}")
print(f"Completed: {stats.get('COMPLETED', 0)}")
```

## Database Schema

The SQLite database is defined in `scripts/init_db.sql`:

```sql
CREATE TABLE worklist_items (
    accession_number TEXT PRIMARY KEY,

    -- Patient demographics
    patient_id TEXT NOT NULL,
    patient_name TEXT NOT NULL,              -- DICOM format: FAMILY^GIVEN
    patient_birth_date TEXT NOT NULL,        -- YYYYMMDD format
    patient_sex TEXT,                        -- M/F/O

    -- Scheduling information
    scheduled_date TEXT NOT NULL,            -- YYYYMMDD format
    scheduled_time TEXT NOT NULL,            -- HHMMSS format
    modality TEXT NOT NULL,                  -- e.g., MG for mammography

    -- Procedure details
    study_description TEXT,
    procedure_code TEXT,

    -- Status tracking (updated via MPPS)
    status TEXT DEFAULT 'SCHEDULED' CHECK(status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'DISCONTINUED')),

    -- DICOM identifiers
    study_instance_uid TEXT,
    mpps_instance_uid TEXT,

    -- Audit trail
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    -- Link to source message from relay listener
    source_message_id TEXT
);
```

**Indexes** optimize common query patterns:
- `idx_worklist_date_modality`: For MWL C-FIND queries by date and modality
- `idx_worklist_status`: For filtering by procedure status
- `idx_worklist_study_uid`: For MPPS lookups
- `idx_worklist_patient_id`: For patient-specific queries

## MPPS Status Flow

The database tracks procedure lifecycle via MPPS messages:

1. **Initial State**: Worklist item created with `status='SCHEDULED'`
2. **Modality queries**: C-FIND returns items with `status='SCHEDULED'`
3. **Procedure starts**: N-CREATE updates `status='IN_PROGRESS'` and sets `mpps_instance_uid`
4. **Procedure completes**: N-SET updates `status='COMPLETED'` or `'DISCONTINUED'`

All status changes are automatically logged with `updated_at` timestamps.

## Ports

| Port | Service | Description |
|------|---------|-------------|
| 8042 | HTTP | Orthanc Web UI and REST API |
| 4242 | DICOM | Orthanc main DICOM service |
| 4243 | DICOM | Modality Worklist / MPPS service |

## Configuration

### Modality Configuration

Configure your mammography modality with:
- **Worklist SCP AE Title**: `ORTHANC_MWL`
- **Worklist SCP Host**: `<gateway-ip>`
- **Worklist SCP Port**: `4243`

### Orthanc Configuration (`orthanc.json`)

Key settings:
```json
{
  "MPPSAet": "ORTHANC_MWL",          // AE Title for worklist server
  "DicomPortMPPS": 4243,             // Port for worklist/MPPS
  "Plugins": [
    "/usr/share/orthanc/plugins-available/libOrthancPython.so"
  ],
  "PythonScript": "/scripts/worklist_server.py",
  "PythonVerbose": true,             // Enable detailed logging
  "DicomCheckCalledAet": false,      // Accept any AE Title
  "AuthenticationEnabled": false     // Disable for POC (enable in prod!)
}
```

## Logs

View server logs:

```bash
# Container logs (includes database initialization)
docker-compose logs -f orthanc-mwl

# Orthanc logs (inside container)
docker-compose exec orthanc-mwl cat /var/log/orthanc/orthanc.log
```

## Development

### Modifying the Python Scripts

The Python scripts are mounted as volumes, so you can edit them without rebuilding:

1. Edit `scripts/worklist_server.py` or `scripts/worklist_storage.py`
2. Restart the container: `docker-compose restart`
3. Check logs for errors: `docker-compose logs -f`

### Modifying the Database Schema

To change the database schema:

1. Edit `scripts/init_db.sql`
2. Remove the existing database volume:
   ```bash
   docker-compose down -v
   ```
3. Rebuild and start:
   ```bash
   docker-compose up --build -d
   ```

### Debugging

Enable verbose logging in `orthanc.json`:
```json
{
  "LogLevel": "verbose",
  "PythonVerbose": true
}
```

### Accessing the Database Directly

```bash
# Open SQLite shell
docker-compose exec orthanc-mwl sqlite3 /var/lib/orthanc/worklist.db

# Inside SQLite shell:
.tables                    # List tables
.schema worklist_items     # Show schema
SELECT * FROM worklist_items;  # Query data
.quit                      # Exit
```

## Integration with Manage Breast Screening Service

This POC demonstrates how the gateway can:

1. **Receive worklist queries** from mammography modalities
2. **Serve worklist item data** from a SQLite database (ready for relay listener integration)
3. **Track procedure status** via MPPS (started, completed)
4. **Update database** with procedure progress in real-time

### Relay Listener Integration

The storage layer is designed for integration with the Azure Relay listener from POC Five:

```python
# In relay listener (when message received from web app)
from worklist_storage import WorklistStorage

storage = WorklistStorage()

# Create worklist item from relay message
storage.add_worklist_item(
    accession_number=message['accession_number'],
    patient_id=message['patient_id'],
    patient_name=message['patient_name'],
    patient_birth_date=message['birth_date'],
    scheduled_date=message['scheduled_date'],
    scheduled_time=message['scheduled_time'],
    modality='MG',
    study_description=message['procedure_description'],
    source_message_id=message['message_id']
)
```

The modality will then see this item in its next worklist query.

### Next Steps

1. **Relay Integration**: Connect Azure Relay listener to write worklist items to database
2. **Bi-directional Status Updates**: Send MPPS status changes back to web app via relay
3. **Authentication**: Enable DICOM security and TLS
4. **High Availability**: Configure for production deployment
5. **Monitoring**: Add health checks and metrics
6. **Image Routing**: Configure DICOM routing rules for received images (if needed)

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs orthanc-mwl

# Verify ports are available
lsof -i :8042
lsof -i :4242
lsof -i :4243
```

### Database initialization errors
```bash
# Check if database was created
docker-compose exec orthanc-mwl ls -la /var/lib/orthanc/

# Verify schema
docker-compose exec orthanc-mwl sqlite3 /var/lib/orthanc/worklist.db ".schema"

# Force re-initialization
docker-compose down -v  # Remove volumes
docker-compose up --build -d
```

### Python plugin errors
```bash
# Verify script syntax
docker-compose exec orthanc-mwl python3 -m py_compile /scripts/worklist_server.py

# Check Python dependencies
docker-compose exec orthanc-mwl pip3 list

# Check if plugin loaded
docker-compose logs orthanc-mwl | grep -i python
```

### Worklist queries return no results
- Check logs for query details: `docker-compose logs orthanc-mwl | grep "Worklist query"`
- Verify modality code matches (e.g., "MG" for mammography)
- Check date format (YYYYMMDD)
- Verify database has items: `docker-compose exec orthanc-mwl sqlite3 /var/lib/orthanc/worklist.db "SELECT * FROM worklist_items;"`
- Check status is `SCHEDULED`: The server only returns scheduled items by default

### MPPS status not updating
- Check logs for MPPS messages: `docker-compose logs orthanc-mwl | grep MPPS`
- Verify accession number in MPPS matches database
- Check database status: `docker-compose exec orthanc-mwl sqlite3 /var/lib/orthanc/worklist.db "SELECT accession_number, status FROM worklist_items;"`

## References

- [Orthanc Documentation](https://orthanc.uclouvain.be/book/)
- [Orthanc Python Plugin](https://orthanc.uclouvain.be/book/plugins/python.html)
- [pynetdicom Documentation](https://pydicom.github.io/pynetdicom/)
- [DICOM Standard - Worklist (Part 4)](https://dicom.nema.org/medical/dicom/current/output/html/part04.html#chapter_K)
- [DICOM Standard - MPPS (Part 3, Annex B.17)](https://dicom.nema.org/medical/dicom/current/output/html/part03.html#sect_B.17)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)

## License

This POC is for demonstration purposes as part of the NHS Digital Breast Screening Service project.
