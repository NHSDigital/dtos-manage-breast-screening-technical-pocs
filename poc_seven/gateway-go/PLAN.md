# Plan: Rewrite Gateway Services from Python to Go

## Overview

Rewrite the 4 Python gateway services to Go, maintaining 100% behavioral compatibility with the Django cloud service. Use a monorepo structure with shared packages for better code organization and reuse.

**Current State:** 4 Python Docker services (~2,700 LOC) with shared modules
**Target State:** Single Go monorepo with 4 compiled binaries and shared packages

## Key Decisions

- **Structure:** Single Go monorepo with cmd/internal/pkg separation
- **DICOM:** `grailbio/go-dicom` (parsing) + `suyashkumar/go-netdicom` (networking)
- **Database:** Keep SQLite with `modernc.org/sqlite` (pure Go, no cgo)
- **Testing:** Essential tests only (unit tests for storage, integration for DICOM)

## Services to Rewrite

1. **worklist-server** (Port 4243): DICOM Worklist C-FIND + MPPS (N-CREATE/N-SET)
2. **pacs-server** (Port 4244): DICOM Storage C-STORE + C-ECHO
3. **relay-listener**: Receives worklist actions from Django via Azure Relay
4. **image-processor**: Polls PACS DB, generates thumbnails, sends to Django

## Go Project Structure

```
gateway-go/
├── cmd/                              # 4 service entry points
│   ├── worklist-server/main.go
│   ├── pacs-server/main.go
│   ├── relay-listener/main.go
│   └── image-processor/main.go
├── internal/                         # Private packages
│   ├── dicom/                        # DICOM handlers (worklist, mpps, store, echo, metadata)
│   ├── storage/                      # Storage layer (worklist, pacs, hash, models)
│   ├── relay/                        # Azure Relay (client, sender, listener, auth, messages)
│   ├── thumbnail/                    # Thumbnail generation (generator, encoder)
│   └── config/                       # Configuration (config, validate)
├── scripts/                          # Reuse existing SQL schemas
│   ├── init_db.sql
│   └── init_pacs_db.sql
├── deployments/                      # Docker configuration
│   ├── Dockerfile.worklist
│   ├── Dockerfile.pacs
│   ├── Dockerfile.relay
│   ├── Dockerfile.processor
│   └── docker-compose.yml
├── test/                             # Integration tests
│   ├── worklist_test.go
│   ├── pacs_test.go
│   └── testdata/
├── go.mod
├── go.sum
├── Makefile
└── README.md
```

## Core Dependencies

```go
require (
    github.com/grailbio/go-dicom v0.0.0-20240815173546-37b6e7e4e1d9  // DICOM parsing
    github.com/suyashkumar/go-netdicom v0.6.2                        // DICOM networking
    modernc.org/sqlite v1.29.1                                       // SQLite (pure Go)
    github.com/gorilla/websocket v1.5.1                              // Azure Relay WebSocket
    github.com/disintegration/imaging v1.6.2                         // Image processing
    github.com/kelseyhightower/envconfig v1.4.0                      // Config parsing
    go.uber.org/zap v1.27.0                                          // Structured logging
    github.com/google/uuid v1.6.0                                    // UUID generation
)
```

## Implementation Phases

### Phase 1: Foundation (Days 1-2)

**Goal:** Shared packages working with tests

1. Create project structure and go.mod
2. Implement `internal/config` - Environment variable parsing and validation
3. Implement `internal/storage/models` - Go structs matching DB schemas
4. Implement `internal/storage/hash` - Hash-based path computation (SHA256)
5. Implement `internal/storage/worklist` - SQLite operations with WAL mode
6. Implement `internal/storage/pacs` - SQLite operations with WAL mode
7. Write unit tests for hash paths and DB CRUD operations

**Critical Files to Reference:**
- `gateway/scripts/pacs_storage.py` - Hash logic, DB operations
- `gateway/scripts/worklist_storage.py` - Worklist DB operations
- `gateway/scripts/init_db.sql` - Worklist schema (reuse exact schema)
- `gateway/scripts/init_pacs_db.sql` - PACS schema (reuse exact schema)

### Phase 2: DICOM Services (Days 3-5)

**Goal:** Both DICOM servers functional

8. Implement `internal/dicom/metadata` - Extract DICOM tags into Go structs
9. Implement `internal/dicom/echo` - C-ECHO verification handler
10. Implement `internal/dicom/worklist` - C-FIND worklist query handler
11. Implement `internal/dicom/mpps` - N-CREATE/N-SET MPPS handlers
12. Implement `internal/dicom/store` - C-STORE handler with hash storage
13. Implement `cmd/worklist-server/main.go` - Port 4243 entry point
14. Implement `cmd/pacs-server/main.go` - Port 4244 entry point
15. Write integration tests with real DICOM C-FIND, C-STORE, MPPS messages

**Critical Files to Reference:**
- `gateway/scripts/standalone_worklist_server.py` - C-FIND handler, MPPS state machine
- `gateway/scripts/pacs_server.py` - C-STORE handler, SOP class support

**Key Requirements:**
- Support 120+ DICOM Storage SOP Classes (like Python version)
- Exact same C-FIND response format
- MPPS status strings must match: "IN PROGRESS", "COMPLETED", "DISCONTINUED"
- Hash-based storage paths must match Python exactly

### Phase 3: Azure Relay (Days 6-7)

**Goal:** Bidirectional relay communication working

16. Implement `internal/relay/auth` - SAS token generation (must match Python exactly)
17. Implement `internal/relay/messages` - JSON schemas for all message types
18. Implement `internal/relay/sender` - Rendezvous pattern sender (MPPS, image events)
19. Implement `internal/relay/listener` - WebSocket listener for worklist actions
20. Implement `cmd/relay-listener/main.go` - Entry point
21. Write relay tests with mock server
22. Manual integration test with Django

**Critical Files to Reference:**
- `gateway/scripts/relay_event_sender.py` - Rendezvous pattern, SAS token generation, critical for Django compatibility
- `gateway/scripts/relay_listener.py` - WebSocket listener, message handling

**Key Requirements:**
- SAS token generation must match Python byte-for-byte
- Rendezvous pattern: Fresh connection per message (no pooling)
- 10-second timeout for acknowledgment
- WebSocket compression MUST be disabled (match Python)
- JSON message schemas must match Django expectations exactly

### Phase 4: Image Processing (Days 8-9)

**Goal:** End-to-end image flow complete

23. Implement `internal/thumbnail/generator` - Exec dcm2img command wrapper
24. Implement `internal/thumbnail/encoder` - Base64 encoding utilities
25. Implement `cmd/image-processor/main.go` - Polling loop, thumbnail generation, relay sending
26. Test with real mammography DICOM images
27. Verify thumbnails match Python output exactly

**Critical Files to Reference:**
- `gateway/scripts/image_listener.py` - Message building, action_id correlation, JSON schema
- `gateway/scripts/thumbnail_generator.py` - dcm2img command parameters

**Key Requirements:**
- dcm2img command: `+oj +Jq25 --min-max-window --scale-y-size 188`
- Thumbnail path must match: `thumbnails/15/77/hash.jpg` (same hash as DICOM)
- Poll every 2 seconds (configurable via env var)
- Process 10 images per batch
- Update `thumbnail_status` atomically to avoid race conditions
- Include all mammography dose fields in relay message

### Phase 5: Docker & Migration (Days 10-12)

**Goal:** Production-ready deployment

28. Create multi-stage Dockerfiles for all 4 services
29. Create docker-compose.yml compatible with existing volumes
30. Test parallel deployment (Go on ports 5243/5244)
31. Performance benchmarking vs Python
32. Cutover testing (stop Python, start Go on 4243/4244)
33. Update documentation (README, migration guide)

**Critical Requirements:**
- Docker images must use same volume paths as Python
- Alpine base with dcmtk installed (for Dockerfile.pacs and Dockerfile.processor)
- Static binary compilation for small image size
- Preserve all environment variables from Python version
- Document rollback procedure

## Database Implementation Details

### SQLite Configuration (Critical)

```go
db, err := sql.Open("sqlite", dbPath)

// Enable WAL mode (CRITICAL for concurrency)
db.Exec("PRAGMA journal_mode=WAL")

// Connection pool settings
db.SetMaxOpenConns(10)
db.SetMaxIdleConns(5)
```

### Schema Compatibility

- Reuse exact SQL schemas from `init_db.sql` and `init_pacs_db.sql`
- No schema changes - ensures perfect compatibility
- All indexes, views, and triggers must be preserved
- Thread-safety handled by Go's `sql.DB` connection pool (simpler than Python's thread-local)

## Azure Relay Implementation Details

### SAS Token Generation (Critical for Compatibility)

Must match Python implementation exactly:

```go
// Hash-based path: SHA256(SOP UID) → first 4 chars → "15/77"
uri := fmt.Sprintf("http://%s/%s", namespace, entityPath)
encodedURI := url.QueryEscape(uri)
expiry := time.Now().Unix() + int64(expirySeconds)
stringToSign := fmt.Sprintf("%s\n%d", encodedURI, expiry)

// HMAC-SHA256
h := hmac.New(sha256.New, []byte(key))
h.Write([]byte(stringToSign))
signature := base64.StdEncoding.EncodeToString(h.Sum(nil))

token := fmt.Sprintf("SharedAccessSignature sr=%s&sig=%s&se=%d&skn=%s",
    encodedURI, url.QueryEscape(signature), expiry, keyName)
```

### Rendezvous Pattern (Critical)

- Create fresh WebSocket connection for each message
- No connection pooling (matches Python behavior)
- Wait for acknowledgment with 10-second timeout
- Close connection after each send
- Disable WebSocket compression: `dialer.EnableCompression = false`

## Testing Strategy

### Unit Tests

- Hash path computation (verify matches Python output)
- SAS token generation (verify format)
- Storage layer CRUD operations
- DICOM metadata extraction

### Integration Tests

- C-FIND worklist queries
- MPPS N-CREATE and N-SET
- C-STORE image storage
- C-ECHO verification
- Hash-based file storage verification
- Database entry verification

### Manual Tests

- Send test DICOM from modality to Go PACS
- Verify thumbnail generation
- Verify relay message sent to Django
- Verify Django creates Study/Series/Image records
- Verify UI updates via SSE

## Migration Strategy

### Phase 1: Shadow Mode (Parallel Deployment)

1. Deploy Go services on different ports (5243, 5244)
2. Configure test modality to send to both Python and Go
3. Monitor logs for discrepancies
4. Compare database entries
5. Compare relay messages
6. Validate identical behavior

### Phase 2: Cutover

1. Stop Python services
2. Update docker-compose.yml to use Go services
3. Start Go services on original ports (4243, 4244)
4. Monitor Django for correct event handling
5. Validate full image workflow
6. Performance monitoring

### Rollback Plan

- Keep Python Docker images available
- Document exact steps to switch back
- All volumes preserved (no data loss)
- Can switch back in <5 minutes

## Compatibility Checklist

Must ensure exact compatibility:

- [ ] Hash-based file paths identical (SHA256, 2-level dirs)
- [ ] Database schema identical (reuse SQL files)
- [ ] SAS token generation identical
- [ ] Relay message JSON schemas identical
- [ ] MPPS status strings identical ("IN PROGRESS" not "IN_PROGRESS")
- [ ] Thumbnail dimensions/quality identical (188px height, Q25)
- [ ] C-FIND response format identical
- [ ] DICOM tag extraction identical (especially dose fields)
- [ ] Event correlation via action_id/source_message_id

## Performance Targets

### Expected Improvements

- **C-STORE throughput:** 50-100 images/sec (5-10x faster than Python)
- **Memory per service:** 10-20MB (5x reduction from 50-100MB)
- **Image processing latency:** ~200ms (2.5x faster than 500ms)
- **Docker image size:** ~20MB (10x reduction from 200MB)
- **Startup time:** <100ms (vs 2-3s Python)

## Critical Files Reference

### Python Source Files to Port

- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/standalone_worklist_server.py`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/pacs_server.py`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/pacs_storage.py`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/worklist_storage.py`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/relay_listener.py`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/relay_event_sender.py`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/image_listener.py`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/thumbnail_generator.py`

### Database Schemas (Reuse Verbatim)

- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/init_db.sql`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/scripts/init_pacs_db.sql`

### Docker Configuration

- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/docker-compose.yml`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/Dockerfile.worklist`
- `/Users/grahampengelly/Repos/NHS/dtos-manage-breast-screening-technical-pocs/poc_seven/gateway/Dockerfile.pacs`

## Success Criteria

- [ ] All 4 Go services build and run without errors
- [ ] C-FIND queries return identical results to Python
- [ ] C-STORE stores images in identical hash-based paths
- [ ] MPPS updates database and sends relay events correctly
- [ ] Thumbnails generated with identical dimensions/quality
- [ ] Relay messages match JSON schemas expected by Django
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Performance targets met or exceeded
- [ ] Docker images build successfully
- [ ] Migration completes with zero downtime
- [ ] Django receives and processes all events correctly
- [ ] No data loss or corruption

## Notes

- Go's native concurrency (goroutines) will be cleaner than Python's threading
- Static typing will catch many errors at compile time
- Single binary deployment eliminates dependency management issues
- Smaller Docker images improve deployment speed
- The key challenge is maintaining 100% behavioral compatibility with Django
- Every hash path, database field, and JSON message must match exactly
- Use comprehensive logging to debug any discrepancies during migration
