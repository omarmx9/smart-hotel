#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
while ! nc -z ${POSTGRES_HOST:-postgres} ${POSTGRES_PORT:-5432}; do
    sleep 1
done
echo "PostgreSQL is ready!"

echo "Waiting for InfluxDB..."
while ! nc -z influxdb 8086; do
    sleep 1
done
echo "InfluxDB is ready!"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating initial data..."
python manage.py init_data || true

echo "Starting Daphne server..."
exec daphne -b 0.0.0.0 -p 8000 smart_hotel.asgi:application
