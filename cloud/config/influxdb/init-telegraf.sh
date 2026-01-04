#!/bin/sh
# Script to register Telegraf configuration in InfluxDB
# This runs as part of the docker-entrypoint-initdb.d scripts

set -e

INFLUX_HOST="${INFLUX_HOST:-http://localhost:8086}"
INFLUX_TOKEN="${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN:-admin-token}"
INFLUX_ORG="${DOCKER_INFLUXDB_INIT_ORG:-org}"

# Check if telegraf config already exists
EXISTING=$(influx telegrafs --token "$INFLUX_TOKEN" --org "$INFLUX_ORG" --json 2>/dev/null | grep -c "Smart Hotel Telegraf" || true)

if [ "$EXISTING" -gt 0 ]; then
    echo "Telegraf configuration already exists, skipping..."
    exit 0
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

# MQTT Consumer for Smart Hotel IoT sensors
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = [
    "hotel/+/temperature",
    "hotel/+/humidity",
    "hotel/+/occupancy",
    "hotel/+/door",
    "hotel/+/window",
    "hotel/+/light",
    "hotel/+/hvac",
    "hotel/+/energy",
    "hotel/+/status"
  ]
  qos = 0
  connection_timeout = "30s"
  client_id = "telegraf-smart-hotel"
  data_format = "json"
  json_time_key = "timestamp"
  json_time_format = "unix"
  json_string_fields = ["status", "state", "mode"]
  topic_tag = "topic"
  
  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "hotel/+/+"
    tags = "_/room_id/measurement_type"
TELEGRAF_EOF

# Register the telegraf configuration
echo "Registering Telegraf configuration in InfluxDB..."
influx telegrafs create \
    --name "Smart Hotel Telegraf" \
    --description "Collects system metrics and MQTT sensor data from hotel IoT devices" \
    --org "$INFLUX_ORG" \
    --token "$INFLUX_TOKEN" \
    --file /tmp/telegraf.conf

echo "Telegraf configuration registered successfully!"
