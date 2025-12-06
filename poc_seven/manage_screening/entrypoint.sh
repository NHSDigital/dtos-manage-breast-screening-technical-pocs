#!/bin/sh

echo "Running migrations..."
python manage.py migrate --noinput || { echo "Migration failed!"; exit 1; }
echo "Migrations completed successfully."

echo "Running seed command..."
python manage.py seed || echo "Seed command failed (data may already exist)"
echo "Seed command completed."

exec "$@"
