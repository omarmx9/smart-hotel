# Minimal Compose with Grafana, InfluxDB, Telegraf, Mosquitto

This small setup provides a minimal local stack with bind mounts for data and logs.

## Quick Start

### Production

```bash
docker compose up -d
```

### Development

For development, use the dev compose file which exposes the MRZ testing frontend:

```bash
docker compose -f docker-compose.yml -f docker-compose-dev.yml up -d
```

This enables:
- MRZ Test Frontend: http://localhost:5001/
- Flask debug mode for mrz-backend
- Django debug mode for dashboard and kiosk

## Defaults

- Grafana: http://localhost:3000 (admin/admin)
- InfluxDB: http://localhost:8086 (init user `admin` / password `adminpass`)
- Mosquitto: mqtt://localhost:1883
- Dashboard: http://localhost:8001
- Kiosk: http://localhost:8002
- MRZ Test Frontend: http://localhost:5001 (dev mode only)
