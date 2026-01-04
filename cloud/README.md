# Smart Hotel Cloud Infrastructure

![Docker](https://img.shields.io/badge/Docker-20.10+-blue.svg)
![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2.0+-blue.svg)
![Grafana](https://img.shields.io/badge/Grafana-latest-orange.svg)
![InfluxDB](https://img.shields.io/badge/InfluxDB-2.x-purple.svg)
![MQTT](https://img.shields.io/badge/MQTT-Eclipse%20Mosquitto-yellow.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

> Complete containerized infrastructure stack for the Smart Hotel system, featuring time-series data storage, MQTT messaging, real-time dashboards, and microservice orchestration.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Services](#services)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Authentik Setup](#authentik-setup)
- [Notification System](#notification-system)
- [Network Topology](#network-topology)
- [Data Persistence](#data-persistence)
- [Monitoring & Observability](#monitoring--observability)
- [Development Mode](#development-mode)
- [Troubleshooting](#troubleshooting)

## Overview

The Smart Hotel cloud infrastructure provides all backend services required to run the hotel management system. Using Docker Compose, it orchestrates multiple containers that work together to:

- **Collect sensor data** from ESP32 devices via MQTT
- **Store time-series data** in InfluxDB for historical analysis
- **Visualize metrics** through Grafana dashboards
- **Bridge MQTT to InfluxDB** via Telegraf
- **Serve web applications** for staff (Dashboard) and guests (Kiosk)
- **Process passport images** via the MRZ microservice

## Architecture

```mermaid
flowchart TB
    subgraph EXTERNAL["External Connections"]
        ESP32["ESP32 Devices<br/>MQTT"]
        STAFF["Staff Browser<br/>HTTP"]
        GUESTS["Guest Kiosk<br/>HTTP"]
    end

    subgraph DOCKER["Docker Network"]
        subgraph AUTH_LAYER["Authentication Layer"]
            AUTHENTIK["Authentik<br/>Identity Provider"]
            AUTH_DB["Authentik DB<br/>PostgreSQL"]
            AUTH_REDIS["Redis<br/>Session Store"]
        end

        subgraph DATA_LAYER["Data Layer"]
            MOSQUITTO["Mosquitto<br/>MQTT Broker"]
            TELEGRAF["Telegraf<br/>Data Bridge"]
            INFLUXDB["InfluxDB<br/>Time-Series DB"]
            GRAFANA["Grafana<br/>Visualization"]
            POSTGRES["PostgreSQL<br/>Rooms/Reservations"]
        end
        
        subgraph APP_LAYER["Application Layer"]
            DASHBOARD["Dashboard<br/>Django/ASGI"]
            NODERED["Node-RED<br/>Notification Gateway"]
        end
        
        subgraph NOTIFY["Notification Services"]
            TELEGRAM["Telegram<br/>Bot API"]
            SMS["Twilio<br/>SMS API"]
        end
        
        subgraph KIOSK_NET["Kiosk Network (Isolated)"]
            KIOSK["Kiosk App<br/>Django"]
            MRZ["MRZ Backend<br/>Flask<br/>internal"]
        end
    end

    ESP32 <-->|MQTT| MOSQUITTO
    STAFF -->|HTTP| DASHBOARD
    STAFF -->|OIDC| AUTHENTIK
    GUESTS -->|HTTP| KIOSK
    
    MOSQUITTO --> TELEGRAF
    TELEGRAF --> INFLUXDB
    INFLUXDB --> GRAFANA
    GRAFANA -->|OAuth| AUTHENTIK
    
    AUTHENTIK --> AUTH_DB
    AUTHENTIK --> AUTH_REDIS
    
    DASHBOARD <--> POSTGRES
    DASHBOARD <--> MOSQUITTO
    DASHBOARD --> NODERED
    DASHBOARD --> INFLUXDB
    DASHBOARD -->|OIDC| AUTHENTIK
    
    NODERED --> TELEGRAM
    NODERED --> SMS
    NODERED <--> MOSQUITTO
    
    KIOSK --> MRZ
```

### Data Flow Diagrams

#### Sensor Data Flow

```mermaid
flowchart LR
    A["ESP32<br/>Sensor"] -->|MQTT Publish| B["Mosquitto<br/>Broker"]
    B --> C["Telegraf<br/>Agent"]
    C -->|Write| D["InfluxDB<br/>Bucket"]
    D --> E["Grafana<br/>Panel"]
    D --> F["Dashboard<br/>Django"]
    E --> G["Staff View"]
    F --> H["Real-time UI"]
```

#### Control Command Flow

```mermaid
flowchart LR
    A["Django<br/>Dashboard"] -->|MQTT Publish| B["Mosquitto<br/>Broker"]
    B -->|Subscribe| C["ESP32<br/>Device"]
    C -->|Execute| D["ACTIONS"]
```

## Services

### Core Infrastructure

| Service | Image | Port | Description |
|---------|-------|------|-------------|
| **InfluxDB** | `influxdb:2-alpine` |  | Time-series database for sensor data |
| **PostgreSQL** | `postgres:16-alpine` |  | Relational database for rooms/reservations |
| **Mosquitto** | `eclipse-mosquitto:latest` |  | MQTT broker for IoT messaging |
| **Telegraf** | `telegraf:alpine` |  | MQTT → InfluxDB data bridge |
| **Grafana** | `grafana/grafana:latest` |  | Metrics visualization |

### Authentication & Messaging

| Service | Image | Port | Description |
|---------|-------|------|-------------|
| **Authentik Server** | `ghcr.io/goauthentik/server` | 9000, 9443 | Identity provider (OIDC/OAuth2) |
| **Authentik Worker** | `ghcr.io/goauthentik/server` | - | Background task processor |
| **Authentik DB** | `postgres:16-alpine` | - | Authentik PostgreSQL database |
| **Authentik Redis** | `redis:alpine` | - | Session store & cache |
| **Node-RED** | `nodered/node-red:latest` | 1880 | Notification gateway (Telegram + SMS) |

### Application Services

| Service | Build Context | Port | Description |
|---------|---------------|------|-------------|
| **Dashboard** | `../dashboards/django_app` | 8001 | Staff management interface |
| **Kiosk** | `../kiosk` | 8002 | Guest self check-in |
| **MRZ Backend** | `../kiosk/app` | 5000 (dev only) | Passport processing API |

## Quick Start

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB+ available RAM
- OpenSSL (for secret generation)

### Production Deployment

```bash
# Clone the repository
git clone https://github.com/yourusername/smart-hotel.git
cd smart-hotel/cloud

# Run the interactive setup wizard
./setup.sh

# Start all services
docker compose up --build -d

# Check service status
docker compose ps

# View logs
docker compose logs -f
```

### Setup Wizard Options

The `./setup.sh` script provides an interactive wizard to configure:

| Feature | Description |
|---------|-------------|
| **Port Conflict Detection** | Automatically scans for port conflicts and offers remapping |
| **MQTT Authentication** | Optional username/password authentication for MQTT broker |
| **MQTT TLS** | Optional TLS encryption with self-signed or custom certificates |
| **External URL** | Configure domain for production deployment |

#### Port Conflict Resolution

The setup wizard automatically detects if any required ports are in use and offers three options:

1. **Remap** - Use a different port (e.g., 9443 → 9444)
2. **Disable** - Skip the port binding for that service
3. **Keep** - Use the default port anyway (may fail at startup)

Remapped ports are automatically saved to `.env` and displayed in the summary.

All core services (Authentik, InfluxDB, Grafana) are **pre-configured automatically** via:
- Authentik blueprints (auto-provision OAuth2 providers, groups, and guest enrollment)
- InfluxDB initialization scripts (create buckets, retention policies, and Telegraf configs)
- Grafana provisioning (datasources and default dashboards)

### Updating the Stack

Use the update script for safe updates with automatic backups:

```bash
./update.sh
```

The update script will:
1. Create backups of PostgreSQL and InfluxDB databases
2. Pull latest Docker images
3. Run database migrations
4. Perform health checks

### Development Mode

Development mode exposes additional debugging features:

```bash
# Start with development overrides
docker compose -f docker-compose.yml -f docker-compose-dev.yml up --build -d
```

**Development features:**
- MRZ Test Frontend exposed at port 5000
- Flask debug mode with auto-reload
- Django debug mode enabled
- Verbose logging

### Stopping Services

```bash
# Stop all services (preserves data)
docker compose down

# Stop and remove volumes (⚠️ deletes all data)
docker compose down -v
```

## Configuration

### Service Endpoints

All ports are configurable via `.env` - the setup wizard can remap ports if conflicts are detected.

| Service | Default URL | Credentials |
|---------|-------------|-------------|
| Authentik | http://localhost:9000 | `akadmin` / from `AUTHENTIK_BOOTSTRAP_PASSWORD` |
| Authentik HTTPS | https://localhost:9443 | Same as above |
| Grafana | http://localhost:3000 | From `.env` (or via Authentik SSO) |
| InfluxDB | http://localhost:8086 | From `.env` |
| Dashboard | http://localhost:8001 | Via Authentik SSO |
| Kiosk | http://localhost:8002 | (no auth for guests) |
| Node-RED | http://localhost:1880/api/health | Headless (no UI) |
| Mosquitto | mqtt://localhost:1883 | Optional auth via setup.sh |
| Mosquitto TLS | mqtts://localhost:8883 | Optional, configure via setup.sh |
| Mosquitto WS | ws://localhost:9001 | WebSocket for browser clients |

### MQTT Security (Optional)

The setup wizard can configure MQTT security:

#### Password Authentication

```bash
# Configured via setup.sh or manually:
docker exec mosquitto mosquitto_passwd -c /mosquitto/config/passwd mqtt_user
```

When enabled, all MQTT clients (ESP32 devices, Telegraf, Dashboard) must authenticate.

#### TLS Encryption

```bash
# Generate self-signed certificates (done automatically by setup.sh):
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout config/mosquitto/certs/server.key \
  -out config/mosquitto/certs/server.crt
```

TLS port 8883 is enabled when certificates are present.

### Environment Variables

All configuration is managed via the `.env` file. Run `./generate-env.sh` to create one with secure random secrets.

See `.env.example` for complete documentation of all variables.

#### Key Configuration Categories

| Category | Variables | Description |
|----------|-----------|-------------|
| **Database** | `POSTGRES_*` | Main PostgreSQL settings |
| **InfluxDB** | `INFLUX_*` | Time-series database |
| **Authentik** | `AUTHENTIK_*`, `OIDC_*` | Identity provider |
| **Grafana** | `GRAFANA_*` | Visualization dashboard |
| **MQTT** | `MQTT_*` | Optional auth and TLS settings |
| **Node-RED** | `NODERED_*`, `TWILIO_*` | SMS gateway |
| **Telegram** | `TELEGRAM_*` | Bot notifications |
| **Kiosk** | `KIOSK_*` | Guest registration terminal |
| **Sessions** | `SESSION_COOKIE_AGE` | 7 days default for guests |

#### External Services (Manual Configuration)

| Service | How to Get Credentials |
|---------|------------------------|
| **Twilio** | https://console.twilio.com/ |
| **Telegram** | Create bot via @BotFather |
| **SMTP** | Your email provider |

### Configuration Files

```
cloud/
├── .env                     # Environment variables (generate with ./generate-env.sh)
├── .env.example             # Template with documentation
├── generate-env.sh          # Script to generate secure .env
├── setup.sh                 # Interactive setup wizard (MQTT, TLS, etc.)
├── update.sh                # Safe update script with backups
├── docker-compose.yml       # Main compose file
├── docker-compose-dev.yml   # Development overrides
└── config/
    ├── authentik/
    │   └── blueprints/      # Auto-provision OAuth2, groups, flows
    ├── grafana/
    │   └── provisioning/    # Grafana datasources and dashboards
    ├── influxdb/
    │   ├── config.yml       # InfluxDB configuration
    │   └── init-telegraf.sh # Bucket creation and Telegraf setup
    ├── mosquitto/
    │   ├── mosquitto.conf   # MQTT broker settings
    │   ├── passwd           # Password file (if auth enabled)
    │   └── certs/           # TLS certificates (if TLS enabled)
    ├── nodered/
    │   ├── settings.js      # Node-RED headless config
    │   └── flows.json       # Notification gateway flows
    └── telegraf/
        └── telegraf.conf    # MQTT→InfluxDB bridge config
```

## Authentik Setup

Authentik provides centralized identity management for the Smart Hotel system. **Most configuration is automatic** via blueprints.

### Pre-Configured Components

The following are created automatically on first startup:

| Component | Description |
|-----------|-------------|
| **OAuth2 Provider** (`smart-hotel`) | OIDC provider for Dashboard authentication |
| **OAuth2 Provider** (`grafana`) | OIDC provider for Grafana SSO |
| **Application** (`Smart Hotel`) | Main application with both providers |
| **Group** (`Hotel Staff`) | Admin/staff access group |
| **Group** (`Hotel Guests`) | Guest access group with limited permissions |
| **Service Account** (`kiosk-service`) | API token for kiosk guest account creation |
| **Guest Enrollment Flow** | Self-service guest registration flow |

### Default Admin Credentials

The initial admin account is created automatically:

| Setting | Value | Source |
|---------|-------|--------|
| Username | `akadmin` | Authentik default |
| Password | `changeme` | `AUTHENTIK_BOOTSTRAP_PASSWORD` in `.env` |
| Email | `admin@smarthotel.local` | `AUTHENTIK_BOOTSTRAP_EMAIL` in `.env` |

**⚠️ Important:** Change the admin password after first login!

```bash
# Access Authentik admin at:
open http://localhost:9000/if/admin/
```

### Creating Staff Users

1. Go to **Directory** → **Users** → **Create**
2. Fill in user details
3. Go to **Groups** tab → Add to `Hotel Staff`
4. User can now log in at http://localhost:8001

### Guest Account API

The kiosk application can create temporary guest accounts via API:

```bash
# Create a guest account
curl -X POST http://localhost:8002/api/guest/create/ \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "room_number": "101",
    "checkout_date": "2026-01-15"
  }'

# Deactivate a guest account
curl -X POST http://localhost:8002/api/guest/deactivate/ \
  -H "Content-Type: application/json" \
  -d '{"username": "guest_john_doe_20260108"}'
```

### Manual Configuration (Optional)

If you need to customize the OAuth2 settings:

1. Go to **Admin Interface** → **Applications** → **Providers**
2. Edit `smart-hotel` provider
3. Adjust Redirect URIs for your domain:
   ```
   https://yourdomain.com/accounts/oidc/callback/
   ```

### Session Configuration

Sessions are configured for hotel guest convenience:

| Setting | Default | Purpose |
|---------|---------|---------|
| `SESSION_COOKIE_AGE` | 604800 (7 days) | Session lifetime |
| `OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS` | 900 (15 min) | Token refresh |

Adjust in `.env` as needed.

## Notification System

The notification system uses Node-RED as a unified gateway for Telegram and SMS notifications with automatic fallback logic.

### Architecture

```mermaid
flowchart LR
    subgraph DASHBOARD["Django Dashboard"]
        API["Notification API"]
        MQTT_PUB["MQTT Publisher"]
    end
    
    subgraph NODERED["Node-RED Gateway"]
        RECV["MQTT Receiver"]
        LOGIC["Fallback Logic"]
        TG["Telegram Sender"]
        SMS["SMS Sender"]
        FAIL["Failure Handler"]
    end
    
    subgraph EXTERNAL["External Services"]
        TELEGRAM["Telegram API"]
        TWILIO["Twilio API"]
    end
    
    API --> MQTT_PUB
    MQTT_PUB -->|hotel/notifications/send| RECV
    RECV --> LOGIC
    LOGIC -->|Try first| TG
    LOGIC -->|Fallback| SMS
    TG --> TELEGRAM
    SMS --> TWILIO
    TG -->|Failed| SMS
    SMS -->|Failed| FAIL
    FAIL -->|hotel/notifications/failure| DASHBOARD
```

### Notification Flow

1. Dashboard publishes notification to MQTT topic `hotel/notifications/send`
2. Node-RED receives notification and checks configured services
3. **If Telegram configured**: Try Telegram first
4. **If Telegram fails or not configured**: Try SMS
5. **If both fail**: Publish failure to `hotel/notifications/failure`
6. Results published to `hotel/notifications/result`

### Configuration

Set up notification services in `.env`:

```bash
# Telegram Bot (optional)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=123456789

# Twilio SMS (optional)
TWILIO_ACCOUNT_SID=ACxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxx
TWILIO_PHONE_NUMBER=+1234567890
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Service health and configuration status |
| `/api/status` | GET | Detailed statistics |
| `/api/notify` | POST | Send notification (HTTP alternative) |

### MQTT Topics

| Topic | Direction | Payload |
|-------|-----------|---------|
| `hotel/notifications/send` | IN | `{type, message, recipient, priority}` |
| `hotel/notifications/result` | OUT | `{id, success, method, attempts}` |
| `hotel/notifications/failure` | OUT | `{id, reason, attempts}` |
| `hotel/alerts/#` | IN | System alerts (gas, temperature, etc.) |

#### ESP32-CAM Topics (Face Recognition)

| Topic | Direction | Payload |
|-------|-----------|---------|
| `hotel/kiosk/+/face/recognized` | IN | `{name, confidence, timestamp, device}` |
| `hotel/kiosk/+/face/unknown` | IN | `{confidence, timestamp, device}` |
| `hotel/kiosk/+/status` | IN | `{status, uptime, model_ready, free_heap}` |
| `hotel/kiosk/+/heartbeat` | IN | `{uptime, free_heap, wifi_rssi}` |
| `hotel/kiosk/<id>/control` | OUT | `{command: "status"|"restart"|"capture"}` |

### Notification Payload

```json
{
  "type": "guest_credentials",
  "message": "Welcome! WiFi: HotelGuest, Password: abc123",
  "recipient": {
    "phone": "+1234567890",
    "chat_id": "123456789"
  },
  "priority": "normal",
  "metadata": {
    "room": "101",
    "guest": "John Doe"
  }
}
```

### Dashboard Integration

The Notifications page (`/notifications/`) provides:
- Real-time service status
- Delivery statistics
- Send test notifications (admin only)
- View recent failures

## Network Topology

### Docker Networks

The compose file creates two isolated networks:

```mermaid
flowchart TB
  subgraph default_network ["default network"]
    influxdb
    telegraf
    mosquitto
    grafana
    dashboard
    postgres
    influxdb <--> telegraf
    telegraf <--> mosquitto
    grafana <--> influxdb
    dashboard <--> influxdb
    dashboard <--> grafana
    dashboard <--> postgres
  subgraph kiosk_network ["kiosk-network"]
    kiosk
    mrz_backend
    kiosk --> mrz_backend
  end
```

### Port Mappings

| Host Port | Container | Service |
|-----------|-----------|---------|
| 3000 | 3000 | Grafana web UI |
| 8086 | 8086 | InfluxDB API |
| 8001 | 8000 | Dashboard Django |
| 8002 | 8000 | Kiosk Django |
| 1883 | 1883 | MQTT TCP |
| 9001 | 9001 | MQTT WebSocket |
| 5000 (dev) | 5000 | MRZ test frontend |

## Data Persistence

### Named Volumes

All persistent data is stored in Docker named volumes:

| Volume | Service | Purpose |
|--------|---------|---------|
| `influxdb-data` | InfluxDB | Time-series data |
| `influxdb-config` | InfluxDB | Configuration |
| `grafana-logs` | Grafana | Log files |
| `mosquitto-data` | Mosquitto | Retained messages |
| `mosquitto-logs` | Mosquitto | Broker logs |
| `postgres-data` | PostgreSQL | Rooms, reservations |
| `authentik-db` | Authentik DB | User data, config |
| `authentik-redis` | Authentik Redis | Sessions, cache |
| `authentik-media` | Authentik | Uploaded media |
| `authentik-templates` | Authentik | Custom templates |
| `authentik-certs` | Authentik | SSL certificates |
| `nodered-data` | Node-RED | Flow data |
| `kiosk_data` | Kiosk | SQLite database |
| `kiosk_media` | Kiosk | Uploaded files |
| `mrz_logs` | MRZ Backend | Processed passports |

### Backup & Restore

```bash
# Backup InfluxDB data
docker compose exec influxdb influx backup /var/lib/influxdb2/backup

# Backup PostgreSQL
docker compose exec postgres pg_dump -U smarthotel smarthotel > backup.sql

# Restore PostgreSQL
docker compose exec -T postgres psql -U smarthotel smarthotel < backup.sql
```

## Monitoring & Observability

### Grafana Dashboards

Pre-configured dashboards for:
- **Room Sensors**: Temperature, humidity, luminosity per room
- **System Health**: Container metrics, network traffic
- **MQTT Traffic**: Message rates, topic activity

Access Grafana at http://localhost:3000

### InfluxDB Queries

Query sensor data directly:

```flux
from(bucket: "bucket")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "mqtt_consumer")
  |> filter(fn: (r) => r.topic =~ /hotel\/room\/.*\/temperature/)
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f dashboard

# Last 100 lines
docker compose logs --tail=100 mosquitto
```

## Development Mode

### docker-compose-dev.yml

The development override file adds:

```yaml
services:
  mrz-backend:
    ports:
      - "5000:5000"  # Expose test frontend
    environment:
      FLASK_DEBUG: '1'
      
  dashboard:
    environment:
      DJANGO_DEBUG: 'True'
      
  kiosk:
    environment:
      DEBUG: '1'
```

### Hot Reload

For active development, mount source code:

```yaml
services:
  dashboard:
    volumes:
      - ../dashboards/django_app:/app
```

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Find process using port
sudo lsof -i :3000
# Kill process or change port in docker-compose.yml
```

**Database connection failed:**
```bash
# Check if postgres is ready
docker compose logs postgres
# Restart dependent services
docker compose restart dashboard
```

**MQTT not receiving messages:**
```bash
# Test MQTT connectivity
docker compose exec mosquitto mosquitto_sub -t '#' -v
# Check Telegraf logs
docker compose logs telegraf
```

**InfluxDB token issues:**
```bash
# Recreate Telegraf user
docker compose exec influxdb /docker-entrypoint-initdb.d/init-telegraf.sh
```

### Health Checks

```bash
# Check all container status
docker compose ps

# Test InfluxDB
curl http://localhost:8086/health

# Test Mosquitto
mosquitto_pub -h localhost -t "test" -m "hello"

# Test Dashboard
curl http://localhost:8001/api/rooms/
```

### Rebuilding Services

```bash
# Rebuild single service
docker compose build dashboard
docker compose up -d dashboard

# Full rebuild with no cache
docker compose build --no-cache
docker compose up -d
```

## Security Notes

⚠️ **Production Checklist:**

1. **Run `./generate-env.sh`** to create secure secrets automatically
2. **Complete Authentik setup** - create admin account and OAuth2 provider
3. **Configure external URLs** - update `AUTHENTIK_EXTERNAL_URL` for your domain
4. **Enable HTTPS** - configure reverse proxy (nginx, traefik) for all services
5. **Set up Twilio** for SMS notifications (optional)
6. **Configure Telegram** for admin alerts (optional)
7. **Enable MQTT authentication** in mosquitto.conf for IoT security
8. **Regular backups** of all volumes
9. **Update Authentik** regularly for security patches
10. **Review session timeouts** - default 7 days may be too long for some deployments
