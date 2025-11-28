#!/bin/bash
set -e

# Database initialization
DB_PATH="${PACS_DB_PATH:-/var/lib/pacs/pacs.db}"
DB_DIR=$(dirname "$DB_PATH")
INIT_SQL="/scripts/init_pacs_db.sql"

echo "=================================================="
echo "Standalone DICOM PACS Server - Initialization"
echo "=================================================="
echo ""
echo "Configuration:"
echo "  AE Title: ${PACS_AET:-SCREENING_PACS}"
echo "  Port: ${PACS_PORT:-4244}"
echo "  Database: $DB_PATH"
echo "  Storage: ${PACS_STORAGE_PATH:-/var/lib/pacs/storage}"
echo "  Log Level: ${LOG_LEVEL:-INFO}"
echo ""

# Ensure database directory exists
mkdir -p "$DB_DIR"

# Check if database needs initialization
if [ ! -f "$DB_PATH" ]; then
    echo "📊 Database not found. Initializing PACS database..."

    if [ -f "$INIT_SQL" ]; then
        sqlite3 "$DB_PATH" < "$INIT_SQL"
        echo "✅ Database initialized successfully"
    else
        echo "⚠️  Warning: init_pacs_db.sql not found, creating empty database"
        sqlite3 "$DB_PATH" "VACUUM;"
    fi
else
    echo "✅ Database exists at $DB_PATH"
fi

# Show statistics if database has data
echo ""
echo "📈 PACS statistics:"
sqlite3 "$DB_PATH" "SELECT 'Stored Instances: ' || COUNT(*) FROM stored_instances WHERE status='STORED';" 2>/dev/null || echo "Stored Instances: 0"
sqlite3 "$DB_PATH" "SELECT 'Total Studies: ' || COUNT(DISTINCT study_instance_uid) FROM stored_instances WHERE status='STORED';" 2>/dev/null || echo "Total Studies: 0"
sqlite3 "$DB_PATH" "SELECT 'Total Patients: ' || COUNT(DISTINCT patient_id) FROM stored_instances WHERE status='STORED';" 2>/dev/null || echo "Total Patients: 0"

echo ""
echo "=================================================="
echo "Starting DICOM PACS Server..."
echo "=================================================="
echo ""

# Execute the command passed to the container
exec "$@"
