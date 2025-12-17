# Docker Deployment

This directory contains Dockerfiles for all 4 Go gateway services.

## Quick Start

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your Azure Relay credentials
nano .env

# 3. Build and start all services
make docker-start

# 4. View logs
make docker-logs

# 5. Stop services
make docker-down
```

## Services

### worklist-server (Port 4243 → 5243)
**Dockerfile**: `Dockerfile.worklist`
**Purpose**: DICOM Modality Worklist Server + MPPS handler
**Image Size**: ~15 MB (Alpine-based)
**Dependencies**: SQLite, ca-certificates

### pacs-server (Port 4244 → 5244)
**Dockerfile**: `Dockerfile.pacs`
**Purpose**: DICOM Storage (C-STORE) server
**Image Size**: ~15 MB (Alpine-based)
**Dependencies**: SQLite, ca-certificates

### relay-listener (No port)
**Dockerfile**: `Dockerfile.relay`
**Purpose**: Receives worklist actions from Django via Azure Relay
**Image Size**: ~15 MB (Alpine-based)
**Dependencies**: SQLite, ca-certificates

### image-processor (No port)
**Dockerfile**: `Dockerfile.processor`
**Purpose**: Polls PACS, generates thumbnails, sends to Django
**Image Size**: ~45 MB (Debian-based with dcmtk)
**Dependencies**: dcmtk (for dcm2img), SQLite, ca-certificates

## Architecture

All Dockerfiles use **multi-stage builds**:
1. **Build stage**: golang:1.23-alpine - compiles Go binaries
2. **Runtime stage**: alpine:3.19 or debian:12-slim - runs binaries

Benefits:
- Small image sizes (15-45 MB vs 200+ MB Python)
- Fast startup (<100ms vs 2-3s Python)
- Static binaries (no runtime dependencies except dcmtk for processor)
- Security: runs as non-root user (uid 1000)

## Port Configuration

By default, Go services use ports 5243/5244 for **parallel testing** with Python:
- Python: 4243 (worklist), 4244 (pacs)
- Go: 5243 (worklist), 5244 (pacs)

To **replace** Python services, set environment variables:
```bash
export WORKLIST_PORT=4243
export PACS_PORT=4244
make docker-start
```

## Volumes

Volumes are suffixed with `-go` to avoid conflicts with Python:
- `worklist-db-go`: Worklist database
- `pacs-db-go`: PACS database
- `pacs-storage-go`: DICOM files
- Shared with host: `./pacs_data/thumbnails` (for easy access)

## Environment Variables

Required (Azure Relay):
```bash
AZURE_RELAY_NAMESPACE=your-namespace.servicebus.windows.net
AZURE_RELAY_HYBRID_CONNECTION=worklist-actions
AZURE_RELAY_EVENTS_HYBRID_CONNECTION=gateway-events
AZURE_RELAY_KEY_NAME=RootManageSharedAccessKey
AZURE_RELAY_SHARED_ACCESS_KEY=your-key-here
```

Optional (with defaults):
```bash
# DICOM Configuration
WORKLIST_AET=SCREENING_MWL
PACS_AET=SCREENING_PACS

# Image Processing
IMAGE_POLL_INTERVAL=2
IMAGE_BATCH_SIZE=10
THUMBNAIL_QUALITY=25
THUMBNAIL_HEIGHT=188

# Logging
LOG_LEVEL=INFO
```

## Make Commands

```bash
# Build images
make docker-build

# Start services (detached)
make docker-up

# View logs
make docker-logs

# Restart services
make docker-restart

# Check status
make docker-ps

# Stop services
make docker-down

# Clean everything (including volumes!)
make docker-clean
```

## Healthchecks

Services include healthchecks:
- `worklist-server`: Checks database file exists
- `pacs-server`: Checks database file exists

View health status:
```bash
docker-compose ps
```

## Troubleshooting

### Build fails with "go.mod not found"
Ensure you're running from the repository root:
```bash
cd gateway-go
make docker-build
```

### Services fail to start with "connection refused"
Check Azure Relay credentials in `.env`:
```bash
docker-compose logs relay-listener
```

### Image processor can't generate thumbnails
Verify dcmtk is installed:
```bash
docker-compose exec image-processor which dcm2img
```

### Database permission errors
Ensure volumes have correct permissions:
```bash
docker-compose down -v  # Remove volumes
make docker-start       # Recreate with correct permissions
```

## Testing

### Parallel Testing (Go + Python)
Run both implementations side-by-side:
```bash
# Terminal 1: Python services (ports 4243/4244)
cd ../gateway
docker-compose up

# Terminal 2: Go services (ports 5243/5244)
cd ../gateway-go
make docker-start

# Compare behavior, logs, database entries
```

### Replacement Testing
Stop Python and run Go on original ports:
```bash
# Stop Python
cd ../gateway
docker-compose down

# Start Go on 4243/4244
cd ../gateway-go
export WORKLIST_PORT=4243 PACS_PORT=4244
make docker-start
```

## Production Deployment

For production:
1. Use specific image tags (not `latest`)
2. Configure resource limits in docker-compose.yml
3. Set up log rotation
4. Use external volumes for persistent data
5. Enable TLS for DICOM communication
6. Set up monitoring/alerting
7. Configure backup strategy for databases

## Image Sizes Comparison

| Service | Python | Go |
|---------|--------|-----|
| worklist-server | ~200 MB | ~15 MB |
| pacs-server | ~200 MB | ~15 MB |
| relay-listener | ~200 MB | ~15 MB |
| image-processor | ~250 MB | ~45 MB |
| **Total** | **~850 MB** | **~90 MB** |

**Savings**: ~89% reduction in total image size!
