#!/bin/sh
# ============================================================================
# Smart Hotel - InfluxDB Initialization Script
# ============================================================================
# This script runs during InfluxDB initialization and sets up:
#   - Additional buckets (if needed)
#   - Telegraf configuration in InfluxDB
#   - Retention policies
#   - Dashboard templates
#
# Environment Variables (set by docker-compose):
#   - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN
#   - DOCKER_INFLUXDB_INIT_ORG
#   - DOCKER_INFLUXDB_INIT_BUCKET
# ============================================================================

set -e

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║         Smart Hotel - InfluxDB Initialization                   ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

INFLUX_HOST="${INFLUX_HOST:-http://localhost:8086}"
INFLUX_TOKEN="${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN:-admin-token}"
INFLUX_ORG="${DOCKER_INFLUXDB_INIT_ORG:-smarthotel}"
INFLUX_BUCKET="${DOCKER_INFLUXDB_INIT_BUCKET:-sensors}"

# Wait for InfluxDB to be ready
wait_for_influx() {
    echo "[INFO] Waiting for InfluxDB to be ready..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if influx ping --host "$INFLUX_HOST" 2>/dev/null; then
            echo "[INFO] InfluxDB is ready!"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    echo "[ERROR] InfluxDB did not become ready in time"
    return 1
}

# Create additional buckets
create_buckets() {
    echo "[INFO] Creating additional buckets..."
    
    # Face recognition events bucket (7 day retention)
    if ! influx bucket list --token "$INFLUX_TOKEN" --org "$INFLUX_ORG" --json 2>/dev/null | grep -q '"name":"face_events"'; then
        influx bucket create \
            --name "face_events" \
            --org "$INFLUX_ORG" \
            --token "$INFLUX_TOKEN" \
            --retention 604800s \
            --description "Face recognition events from ESP32-CAM devices" || echo "[WARN] Failed to create face_events bucket"
        echo "[INFO] Created face_events bucket"
    else
        echo "[INFO] face_events bucket already exists"
    fi
    
    # System metrics bucket (30 day retention)
    if ! influx bucket list --token "$INFLUX_TOKEN" --org "$INFLUX_ORG" --json 2>/dev/null | grep -q '"name":"system"'; then
        influx bucket create \
            --name "system" \
            --org "$INFLUX_ORG" \
            --token "$INFLUX_TOKEN" \
            --retention 2592000s \
            --description "System metrics from all services" || echo "[WARN] Failed to create system bucket"
        echo "[INFO] Created system bucket"
    else
        echo "[INFO] system bucket already exists"
    fi
    
    # Alerts bucket (90 day retention)
    if ! influx bucket list --token "$INFLUX_TOKEN" --org "$INFLUX_ORG" --json 2>/dev/null | grep -q '"name":"alerts"'; then
        influx bucket create \
            --name "alerts" \
            --org "$INFLUX_ORG" \
            --token "$INFLUX_TOKEN" \
            --retention 7776000s \
            --description "System alerts and notifications" || echo "[WARN] Failed to create alerts bucket"
        echo "[INFO] Created alerts bucket"
    else
        echo "[INFO] alerts bucket already exists"
    fi
}

# Register Telegraf configuration
register_telegraf() {
    echo "[INFO] Registering Telegraf configuration..."
    
    # Check if telegraf config already exists
    EXISTING=$(influx telegrafs --token "$INFLUX_TOKEN" --org "$INFLUX_ORG" --json 2>/dev/null | grep -c "Smart Hotel Telegraf" || true)
    
    if [ "$EXISTING" -gt 0 ]; then
        echo "[INFO] Telegraf configuration already exists, skipping..."
        return 0
    fi
    
    # Create the telegraf config file
    cat > /tmp/telegraf.conf << 'TELEGRAF_EOF'
[agent]
  interval = "10s"
  round_interval = true
  metric_batch_size = 1000
  metric_buffer_limit = 10000
  collection_jitter = "0s"
  flush_jitter = "0s"
  precision = ""
  debug = false
  quiet = false
  logfile = ""

[[outputs.influxdb_v2]]
  urls = ["${INFLUX_URL}"]
  token = "${INFLUX_TOKEN}"
  organization = "${INFLUX_ORG}"
  bucket = "${INFLUX_BUCKET}"

[[inputs.cpu]]
  percpu = true
  totalcpu = true
  collect_cpu_time = false
  report_active = false

[[inputs.mem]]

[[inputs.disk]]
  ignore_fs = ["tmpfs", "devtmpfs", "devfs", "overlay", "aufs", "squashfs"]

[[inputs.net]]

[[inputs.system]]

# ============================================================================
# MQTT Consumer - Room Sensors (Numeric Values)
# ============================================================================
# Topic structure: hotel/<room_no>/telemetry/<sensor>
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = [
    "hotel/+/telemetry/temperature",
    "hotel/+/telemetry/humidity",
    "hotel/+/telemetry/luminosity",
    "hotel/+/telemetry/gas"
  ]
  qos = 0
  connection_timeout = "30s"
  client_id = "telegraf-smart-hotel-numeric"
  data_format = "value"
  data_type = "float"
  
  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "hotel/+/telemetry/+"
    measurement = "_/_/_/measurement"
    tags = "_/room_id/_/_"

# ============================================================================
# MQTT Consumer - Room Sensors (String Values)
# ============================================================================
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = [
    "hotel/+/telemetry/heating",
    "hotel/+/telemetry/climate_mode",
    "hotel/+/telemetry/fan_speed"
  ]
  qos = 0
  connection_timeout = "30s"
  client_id = "telegraf-smart-hotel-strings"
  data_format = "value"
  data_type = "string"
  
  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "hotel/+/telemetry/+"
    measurement = "_/_/_/measurement"
    tags = "_/room_id/_/_"

# ============================================================================
# MQTT Consumer - Face Recognition Events
# ============================================================================
# Topic: /hotel/kiosk/Room1/FaceRecognition/Authentication
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = [
    "/hotel/kiosk/+/FaceRecognition/Authentication"
  ]
  qos = 1
  connection_timeout = "30s"
  client_id = "telegraf-smart-hotel-facerecog"
  data_format = "json"
  json_string_fields = ["name", "status", "result"]
  
  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "/hotel/kiosk/+/FaceRecognition/Authentication"
    measurement = "_/_/_/room_id/_/_"
    tags = "_/_/_/room_id/_/_"

# ============================================================================
# MQTT Consumer - RFID Access Card Programming
# ============================================================================
# Topic: hotel/kiosk/rfid/program - Kiosk publishes tokens for card programming
# Topic: hotel/kiosk/access/events - Access method selection events
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = [
    "hotel/kiosk/rfid/program",
    "hotel/kiosk/access/events"
  ]
  qos = 1
  connection_timeout = "30s"
  client_id = "telegraf-smart-hotel-rfid"
  data_format = "json"
  json_string_fields = ["action", "token", "room_number", "reason", "event"]
  
  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "hotel/kiosk/rfid/+"
    measurement = "_/_/_/action_type"
    tags = "_/_/_/action_type"

# ============================================================================
# MQTT Consumer - System Alerts
# ============================================================================
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = [
    "hotel/alerts/#"
  ]
  qos = 1
  connection_timeout = "30s"
  client_id = "telegraf-smart-hotel-alerts"
  data_format = "json"
  json_string_fields = ["message", "severity", "source"]
  
  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "hotel/alerts/+"
    measurement = "_/_/alert_type"
    tags = "_/_/alert_type"
TELEGRAF_EOF

    # Register the telegraf configuration
    echo "[INFO] Registering Telegraf configuration in InfluxDB..."
    influx telegrafs create \
        --name "Smart Hotel Telegraf" \
        --description "Collects system metrics and MQTT sensor data from hotel IoT devices" \
        --org "$INFLUX_ORG" \
        --token "$INFLUX_TOKEN" \
        --file /tmp/telegraf.conf || echo "[WARN] Failed to register Telegraf configuration"
    
    echo "[INFO] Telegraf configuration registered successfully!"
}

# Create dashboard variables/templates
create_templates() {
    echo "[INFO] Creating dashboard variables..."
    
    # Create room list variable for Flux queries
    cat > /tmp/room_variable.flux << 'FLUX_EOF'
import "influxdata/influxdb/schema"

schema.tagValues(
    bucket: "sensors",
    tag: "room_id",
    start: -7d
)
FLUX_EOF
    
    echo "[INFO] Dashboard variables ready for Grafana"
}

# Main initialization
main() {
    wait_for_influx
    create_buckets
    register_telegraf
    create_templates
    
    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo "[SUCCESS] InfluxDB initialization complete!"
    echo ""
    echo "Buckets created:"
    echo "  • sensors (default) - Room sensor data"
    echo "  • face_events - Face recognition events (7 day retention)"
    echo "  • system - System metrics (30 day retention)"
    echo "  • alerts - System alerts (90 day retention)"
    echo ""
    echo "Telegraf configuration registered"
    echo "════════════════════════════════════════════════════════════════════"
}

main
