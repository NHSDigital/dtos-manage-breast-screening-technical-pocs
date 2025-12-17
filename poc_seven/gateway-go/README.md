# Gateway Go - DICOM Gateway Services

This is a Go rewrite of the Python gateway services for the NHS Digital Breast Screening Service POC Seven. The gateway provides DICOM worklist, PACS storage, and bidirectional communication with the cloud service via Azure Relay.

## Project Status

**Phase 1: Foundation - COMPLETED ✅**

- [x] Project structure and dependencies
- [x] Configuration management (environment variables)
- [x] Database models matching SQL schemas
- [x] Hash-based storage path computation
- [x] Worklist SQLite storage layer
- [x] PACS SQLite storage layer
- [x] Unit tests for hash functions

**Upcoming Phases:**
- Phase 2: DICOM Services (Worklist C-FIND, PACS C-STORE, MPPS)
- Phase 3: Azure Relay Communication
- Phase 4: Image Processing & Thumbnails
- Phase 5: Docker & Deployment

## Architecture

The system consists of 4 services:

1. **worklist-server** (Port 4243): DICOM Worklist (C-FIND) + MPPS (N-CREATE/N-SET)
2. **pacs-server** (Port 4244): DICOM Storage (C-STORE, C-ECHO)
3. **relay-listener**: Receives worklist actions from Django via Azure Relay
4. **image-processor**: Polls PACS DB, generates thumbnails, sends to Django

### Key Features

- **Hash-based Storage**: Production-like DICOM storage using SHA256-based directory structure
- **SQLite with WAL**: Write-Ahead Logging for better concurrency
- **Thread-safe**: Go's `sql.DB` provides built-in connection pooling
- **Python-compatible**: Exact behavioral compatibility with existing Python implementation

## Directory Structure

```
gateway-go/
├── cmd/                    # Service entry points (4 binaries)
│   ├── worklist-server/
│   ├── pacs-server/
│   ├── relay-listener/
│   └── image-processor/
├── internal/               # Private packages
│   ├── config/             # Configuration ✅
│   ├── storage/            # Storage layer ✅
│   │   ├── models.go       # Database models
│   │   ├── hash.go         # Hash-based paths
│   │   ├── worklist.go     # Worklist storage
│   │   ├── pacs.go         # PACS storage
│   │   └── hash_test.go    # Unit tests
│   ├── dicom/              # DICOM handlers (TODO)
│   ├── relay/              # Azure Relay (TODO)
│   └── thumbnail/          # Thumbnail generation (TODO)
├── scripts/                # SQL schemas
│   ├── init_db.sql
│   └── init_pacs_db.sql
├── deployments/            # Docker configuration (TODO)
├── test/                   # Integration tests (TODO)
├── go.mod
├── go.sum
├── Makefile
├── PLAN.md                 # Detailed implementation plan
└── README.md
```

## Dependencies

- **DICOM**: `grailbio/go-dicom` (parsing), `suyashkumar/dicom` (networking)
- **Database**: `modernc.org/sqlite` (pure Go, no cgo)
- **Communication**: `gorilla/websocket` (Azure Relay)
- **Image Processing**: `disintegration/imaging`
- **Configuration**: `kelseyhightower/envconfig`
- **Logging**: `go.uber.org/zap`

## Building

```bash
# Run tests
go test ./...

# Build all services
make build

# Run tests with coverage
make coverage
```

## Configuration

All services use environment variables (compatible with Python version):

```bash
# Azure Relay
AZURE_RELAY_NAMESPACE=manbrs-gateway-dev.servicebus.windows.net
AZURE_RELAY_HYBRID_CONNECTION=relay-test-hc
AZURE_RELAY_EVENTS_HYBRID_CONNECTION=relay-test-hc-events
AZURE_RELAY_KEY_NAME=RootManageSharedAccessKey
AZURE_RELAY_SHARED_ACCESS_KEY=your-key-here

# Worklist Server
WORKLIST_AET=SCREENING_MWL
WORKLIST_PORT=4243
WORKLIST_DB_PATH=/var/lib/worklist/worklist.db

# PACS Server
PACS_AET=SCREENING_PACS
PACS_PORT=4244
PACS_STORAGE_PATH=/var/lib/pacs/storage
PACS_DB_PATH=/var/lib/pacs/pacs.db

# Image Processor
IMAGE_POLL_INTERVAL=2
IMAGE_BATCH_SIZE=10
THUMBNAIL_QUALITY=25
THUMBNAIL_HEIGHT=188

# General
LOG_LEVEL=INFO
```

## Testing

### Unit Tests

```bash
# Run all tests
go test ./...

# Run with verbose output
go test -v ./internal/storage

# Run with coverage
go test -cover ./...
```

### Hash Compatibility Tests

The hash tests verify that Go implementation produces identical output to Python:

```bash
# Python
>>> import hashlib
>>> hashlib.sha256(b"1.2.826.0.1.3680043.8.498.97304859").hexdigest()
'e2149e50cbb9f6ed3bb62e534cc8497843b79dc823ea002b98319192933c946d'

# Go storage path
>>> ComputeStoragePath("1.2.826.0.1.3680043.8.498.97304859")
"e2/14/e2149e50cbb9f6ed.dcm"  ✅ Matches!
```

## Performance Targets

Compared to Python implementation:

| Metric | Python | Go Target | Improvement |
|--------|--------|-----------|-------------|
| C-STORE throughput | ~10 img/s | ~50-100 img/s | 5-10x |
| Memory per service | 50-100 MB | 10-20 MB | 5x |
| Image processing | ~500 ms | ~200 ms | 2.5x |
| Docker image size | ~200 MB | ~20 MB | 10x |
| Startup time | 2-3 s | <100 ms | 20-30x |

## Development Workflow

1. **Phase 1 (Current)**: Foundation packages - COMPLETED
2. **Phase 2**: DICOM services (C-FIND, C-STORE, MPPS)
3. **Phase 3**: Azure Relay integration
4. **Phase 4**: Image processing and thumbnails
5. **Phase 5**: Docker deployment and testing

## Compatibility Checklist

Critical compatibility requirements with Python version:

- [x] Hash-based file paths (SHA256, 2-level directories)
- [x] Database schema (exact same SQL)
- [x] SQLite WAL mode
- [ ] SAS token generation (Azure Relay)
- [ ] Relay message JSON schemas
- [ ] MPPS status strings ("IN PROGRESS" not "IN_PROGRESS")
- [ ] Thumbnail dimensions (188px height, Q25)
- [ ] C-FIND response format
- [ ] DICOM tag extraction (especially dose fields)

## References

- Python implementation: `../gateway/scripts/`
- Implementation plan: `PLAN.md`
- Database schemas: `scripts/init_db.sql`, `scripts/init_pacs_db.sql`
- DICOM Standard: https://dicom.nema.org/
