#!/bin/sh
set -e

# Database initialization
DB_PATH="${WORKLIST_DB_PATH:-/var/lib/worklist/worklist.db}"
DB_DIR=$(dirname "$DB_PATH")
INIT_SQL="/scripts/init_db.sql"

echo "=================================================="
echo "Go DICOM Worklist Server - Initialization"
echo "=================================================="
echo ""
echo "Configuration:"
echo "  AE Title: ${WORKLIST_AET:-SCREENING_MWL}"
echo "  Port: ${WORKLIST_PORT:-4243}"
echo "  Database: $DB_PATH"
echo "  Log Level: ${LOG_LEVEL:-INFO}"
echo ""

# Ensure database directory exists
mkdir -p "$DB_DIR"

# Check if database needs initialization
TABLE_EXISTS=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name='worklist_items';" 2>/dev/null || echo "")

if [ -z "$TABLE_EXISTS" ]; then
    echo "Database tables not found. Initializing worklist database..."

    if [ -f "$INIT_SQL" ]; then
        sqlite3 "$DB_PATH" < "$INIT_SQL"
        echo "Database initialized successfully"
        echo ""
        echo "Worklist statistics:"
        sqlite3 "$DB_PATH" "SELECT status, COUNT(*) FROM worklist_items GROUP BY status;" 2>/dev/null || echo "No items yet"
    else
        echo "Warning: init_db.sql not found, creating empty database"
        sqlite3 "$DB_PATH" "VACUUM;"
    fi
else
    echo "Database exists at $DB_PATH"
    echo ""
    echo "Worklist statistics:"
    sqlite3 "$DB_PATH" "SELECT status, COUNT(*) FROM worklist_items GROUP BY status;" 2>/dev/null || echo "No items in database"
fi

echo ""
echo "=================================================="
echo "Starting Go DICOM Worklist Server..."
echo "=================================================="
echo ""

# Execute the command passed to the container
exec "$@"
