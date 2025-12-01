#!/bin/bash
set -e

# Database initialization
DB_PATH="${WORKLIST_DB_PATH:-/var/lib/worklist/worklist.db}"
DB_DIR=$(dirname "$DB_PATH")
INIT_SQL="/scripts/init_db.sql"

echo "=================================================="
echo "Standalone DICOM Worklist Server - Initialization"
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
if [ ! -f "$DB_PATH" ]; then
    echo "📊 Database not found. Initializing worklist database..."

    if [ -f "$INIT_SQL" ]; then
        sqlite3 "$DB_PATH" < "$INIT_SQL"
        echo "✅ Database initialized successfully"
        echo ""
        echo "📈 Worklist statistics:"
        sqlite3 "$DB_PATH" "SELECT status, COUNT(*) FROM worklist_items GROUP BY status;"
    else
        echo "⚠️  Warning: init_db.sql not found, creating empty database"
        sqlite3 "$DB_PATH" "VACUUM;"
    fi
else
    echo "✅ Database exists at $DB_PATH"
    echo ""
    echo "📈 Worklist statistics:"
    sqlite3 "$DB_PATH" "SELECT status, COUNT(*) FROM worklist_items GROUP BY status;" 2>/dev/null || echo "No items in database"
fi

echo ""
echo "=================================================="
echo "Starting DICOM Worklist Server..."
echo "=================================================="
echo ""

# Execute the command passed to the container
exec "$@"
