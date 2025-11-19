#!/bin/bash
set -e

# Docker entrypoint script for Orthanc MWL Gateway
# Initializes the SQLite worklist database before starting Orthanc

DB_PATH="/var/lib/orthanc/worklist.db"
SCHEMA_PATH="/scripts/init_db.sql"

echo "🚀 Starting Orthanc MWL Gateway..."

# Check if database needs initialization
if [ ! -f "$DB_PATH" ]; then
    echo "📊 Database not found. Initializing worklist database..."

    # Ensure the directory exists
    mkdir -p "$(dirname "$DB_PATH")"

    # Initialize the database with schema
    if [ -f "$SCHEMA_PATH" ]; then
        sqlite3 "$DB_PATH" < "$SCHEMA_PATH"
        echo "✅ Database initialized successfully with schema from $SCHEMA_PATH"
    else
        echo "❌ ERROR: Schema file not found at $SCHEMA_PATH"
        exit 1
    fi
else
    echo "✅ Database already exists at $DB_PATH"
fi

# Show database statistics
echo "📈 Worklist statistics:"
sqlite3 "$DB_PATH" "SELECT status, COUNT(*) as count FROM worklist_items GROUP BY status;" || echo "  (No items yet)"

echo "🏥 Starting Orthanc server..."

# Start Orthanc with the provided configuration
# Pass all arguments to Orthanc (typically the config file path)
exec /usr/local/bin/Orthanc "$@"
