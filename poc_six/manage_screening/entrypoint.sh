#!/bin/sh

echo "Running migrations..."
python manage.py migrate --noinput || { echo "Migration failed!"; exit 1; }
echo "Migrations completed successfully."

echo "Running seed command..."
python manage.py seed || { echo "Seed command failed!"; exit 1; }
echo "Seed completed successfully."

exec "$@"
