# POC Six: Orthanc-based Modality Worklist Server

## Overview

This proof of concept demonstrates running a DICOM Modality Worklist (MWL) server with Modality Performed Procedure Step (MPPS) support on a gateway using Orthanc and Python. The implementation uses:

- **Orthanc**: Open-source DICOM server
- **pynetdicom**: Python library for DICOM networking
- **pydicom**: Python library for working with DICOM data
- **Docker**: Containerized deployment

## Architecture

```
┌─────────────────────────────────────────┐
│   Orthanc Container (Gateway)           │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Orthanc Core                    │  │
│  │  - Web UI (port 8042)            │  │
│  │  - REST API                      │  │
│  │  - DICOM SCP (port 4242)         │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  Python Plugin                   │  │
│  │  worklist_server.py              │  │
│  │                                  │  │
│  │  - MWL Server (port 4243)        │  │
│  │  - C-FIND handler (worklist)     │  │
│  │  - N-CREATE handler (MPPS start) │  │
│  │  - N-SET handler (MPPS complete) │  │
│  │  - C-ECHO handler (verification) │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
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
- Enables Python plugin with path to worklist script
- Sets custom MWL AET (`ORTHANC_MWL`) and port (4243)

### 2. Python Worklist Server (`scripts/worklist_server.py`)
Implements:
- **C-FIND handler**: Responds to worklist queries from modalities
- **N-CREATE handler**: Handles procedure start notifications (MPPS)
- **N-SET handler**: Handles procedure completion/discontinuation (MPPS)
- **C-ECHO handler**: Responds to DICOM ping requests

Currently uses sample data for demonstration. Database integration points are marked with `TODO-DB` comments.

### 3. Docker Configuration
- **Dockerfile**: Builds container with Orthanc and Python dependencies
- **docker-compose.yml**: Orchestrates deployment with volume persistence

## Quick Start

### Build and Run

```bash
cd poc_six

# Build and start the container
docker-compose up --build -d

# View logs
docker-compose logs -f
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

The server currently returns sample data for demonstration:

| Patient ID | Patient Name | Birth Date | Sex | Appointment Date | Time   | Accession | Study Description      |
|------------|--------------|------------|-----|------------------|--------|-----------|------------------------|
| BS001234   | SMITH^JANE   | 1965-03-15 | F   | Today           | 10:00  | ACC001    | Bilateral Mammography  |
| BS005678   | JONES^MARY   | 1970-08-22 | F   | Today           | 11:00  | ACC002    | Screening Mammography  |

## Database Integration

For production use, replace the sample data in `scripts/worklist_server.py`:

### TODO-DB Locations:

1. **`find_worklist()` function** (line ~120):
   - Query database for scheduled appointments
   - Filter by modality, date, and other criteria
   - Return worklist items matching the query

2. **`handle_create()` function** (line ~80):
   - Record that a procedure has started
   - Update appointment status to "In Progress"

3. **`handle_set()` function** (line ~110):
   - Record procedure completion or discontinuation
   - Update appointment status accordingly

### Example Database Schema

```sql
CREATE TABLE appointments (
    appointment_id VARCHAR(50) PRIMARY KEY,
    patient_id VARCHAR(50),
    patient_name VARCHAR(100),
    patient_birth_date DATE,
    patient_sex CHAR(1),
    scheduled_date DATE,
    scheduled_time TIME,
    modality VARCHAR(10),
    study_description VARCHAR(200),
    procedure_code VARCHAR(50),
    status VARCHAR(20) DEFAULT 'SCHEDULED',
    study_instance_uid VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_appointments_date_modality
ON appointments(scheduled_date, modality);
```

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
  "PythonScript": "/scripts/worklist_server.py",
  "PythonVerbose": true,             // Enable detailed logging
  "DicomCheckCalledAet": false,      // Accept any AE Title
  "AuthenticationEnabled": false     // Disable for POC (enable in prod!)
}
```

## Logs

View server logs:

```bash
# Container logs
docker-compose logs -f orthanc-mwl

# Orthanc logs (inside container)
docker-compose exec orthanc-mwl cat /var/log/orthanc/orthanc.log
```

## Development

### Modifying the Python Script

The Python script is mounted as a volume, so you can edit it without rebuilding:

1. Edit `scripts/worklist_server.py`
2. Restart the container: `docker-compose restart`
3. Check logs for errors: `docker-compose logs -f`

### Debugging

Enable verbose logging in `orthanc.json`:
```json
{
  "LogLevel": "verbose",
  "PythonVerbose": true
}
```

## Integration with Manage Breast Screening Service

This POC demonstrates how the gateway can:

1. **Receive worklist queries** from mammography modalities
2. **Serve appointment data** from the central scheduling system
3. **Track procedure status** via MPPS (started, completed)
4. **Update central database** with procedure progress

### Next Steps

1. **Database Integration**: Connect to the actual appointment database
2. **API Integration**: Link with the manage breast screening service API
3. **Authentication**: Enable DICOM security and TLS
4. **High Availability**: Configure for production deployment
5. **Monitoring**: Add health checks and metrics
6. **Image Routing**: Configure DICOM routing rules for images

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

### Python plugin errors
```bash
# Verify script syntax
docker-compose exec orthanc-mwl python3 -m py_compile /scripts/worklist_server.py

# Check Python dependencies (inside container)
docker-compose exec orthanc-mwl pip3 list
```

### Worklist queries return no results
- Check logs for query details
- Verify modality code matches (e.g., "MG" for mammography)
- Check date format (YYYYMMDD)
- Review sample data in `find_worklist()` function

## References

- [Orthanc Documentation](https://orthanc.uclouvain.be/book/)
- [Orthanc Python Plugin](https://orthanc.uclouvain.be/book/plugins/python.html)
- [pynetdicom Documentation](https://pydicom.github.io/pynetdicom/)
- [DICOM Standard - Worklist (Part 4)](https://dicom.nema.org/medical/dicom/current/output/html/part04.html#chapter_K)
- [DICOM Standard - MPPS (Part 3, Annex B.17)](https://dicom.nema.org/medical/dicom/current/output/html/part03.html#sect_B.17)

## License

This POC is for demonstration purposes as part of the NHS Digital Breast Screening Service project.
