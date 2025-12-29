# Minimal Compose with Grafana, InfluxDB, Telegraf, Mosquitto

This small setup provides a minimal local stack with bind mounts for data and logs.

Quick start:

```bash
docker compose up -d
```

Defaults:
- Grafana: http://localhost:3000 (admin/admin)
- InfluxDB: http://localhost:8086 (init user `admin` / password `adminpass`)
- Mosquitto: mqtt://localhost:1883
