#!/usr/bin/env bash
# ============================================================================
# Smart Hotel - Interactive Setup Script
# ============================================================================
# This script guides you through the first-time setup of the Smart Hotel
# cloud infrastructure. It configures:
#   - Environment variables (.env file)
#   - MQTT authentication and optional TLS
#   - InfluxDB initialization
#   - Dashboard initial setup
#
# Usage:
#   ./setup.sh              # Interactive setup
#   ./setup.sh --defaults   # Use defaults (non-interactive, no MQTT auth/TLS)
#   ./setup.sh --help       # Show help
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
MOSQUITTO_CONF="${SCRIPT_DIR}/config/mosquitto/mosquitto.conf"
MOSQUITTO_PASSWD_FILE="${SCRIPT_DIR}/config/mosquitto/passwd"
TLS_DIR="${SCRIPT_DIR}/config/mosquitto/certs"

# Unset environment variables that could override .env values
# This prevents empty shell variables from overriding valid .env settings
unset INFLUX_TOKEN INFLUX_ORG INFLUX_BUCKET MQTT_USER MQTT_PASSWORD 2>/dev/null || true

# Ensure mosquitto passwd is a file not directory
if [ -d "$MOSQUITTO_PASSWD_FILE" ]; then
    rm -rf "$MOSQUITTO_PASSWD_FILE"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Print functions
info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }
header() { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${NC}\n"; }

# Generate a random string
generate_secret() {
    local length=${1:-32}
    openssl rand -base64 "$length" 2>/dev/null | tr -d '/+=' | head -c "$length"
}

# Generate a hex string
generate_hex() {
    local length=${1:-32}
    openssl rand -hex "$length" 2>/dev/null
}

# Generate a secure password with mixed character types
# Requirements: 8+ chars, uppercase, lowercase, numbers, special chars
generate_secure_password() {
    local length=${1:-16}
    # Generate base random string and ensure all character classes present
    local base=$(openssl rand -base64 32 2>/dev/null | tr -d '/+=' | head -c $((length-4)))
    # Add required character classes: uppercase, lowercase, number, special
    local upper=$(echo "ABCDEFGHIJKLMNOPQRSTUVWXYZ" | fold -w1 | shuf | head -1)
    local lower=$(echo "abcdefghijklmnopqrstuvwxyz" | fold -w1 | shuf | head -1)
    local number=$(echo "0123456789" | fold -w1 | shuf | head -1)
    local special=$(echo "!@#%^&*" | fold -w1 | shuf | head -1)
    # Combine and shuffle
    echo "${base}${upper}${lower}${number}${special}" | fold -w1 | shuf | tr -d '\n'
}

# Check dependencies
check_dependencies() {
    local missing=()
    
    if ! command -v openssl &> /dev/null; then
        missing+=("openssl")
    fi
    
    if ! command -v docker &> /dev/null; then
        missing+=("docker")
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing required dependencies: ${missing[*]}"
        echo ""
        echo "Install with:"
        echo "  Ubuntu/Debian: sudo apt install ${missing[*]}"
        echo "  macOS: brew install ${missing[*]}"
        exit 1
    fi
}

# ============================================================================
# Port Conflict Detection and Resolution
# ============================================================================

# Default ports used by Smart Hotel
declare -A DEFAULT_PORTS=(
    ["GRAFANA_PORT"]="3000"
    ["DASHBOARD_PORT"]="8001"
    ["KIOSK_PORT"]="8002"
    ["INFLUX_PORT"]="8086"
    ["MQTT_PORT"]="1883"
    ["MQTT_WS_PORT"]="9001"
    ["MQTT_TLS_PORT"]="8883"
    ["NODERED_PORT"]="1880"
)

# Port descriptions for user display
declare -A PORT_DESCRIPTIONS=(
    ["GRAFANA_PORT"]="Grafana Dashboard"
    ["DASHBOARD_PORT"]="Staff Dashboard"
    ["KIOSK_PORT"]="Guest Kiosk"
    ["INFLUX_PORT"]="InfluxDB"
    ["MQTT_PORT"]="MQTT Broker"
    ["MQTT_WS_PORT"]="MQTT WebSocket"
    ["MQTT_TLS_PORT"]="MQTT TLS"
    ["NODERED_PORT"]="Node-RED"
)

# Store remapped ports
declare -A REMAPPED_PORTS

# Check if a port is in use
is_port_in_use() {
    local port=$1
    if command -v ss &> /dev/null; then
        ss -tuln 2>/dev/null | grep -q ":${port} " && return 0
    elif command -v netstat &> /dev/null; then
        netstat -tuln 2>/dev/null | grep -q ":${port} " && return 0
    elif command -v lsof &> /dev/null; then
        lsof -i ":${port}" &>/dev/null && return 0
    fi
    return 1
}

# Get process using a port
get_port_process() {
    local port=$1
    if command -v ss &> /dev/null; then
        ss -tulnp 2>/dev/null | grep ":${port} " | sed 's/.*users:(("\([^"]*\)".*/\1/' | head -1
    elif command -v lsof &> /dev/null; then
        lsof -i ":${port}" 2>/dev/null | awk 'NR==2 {print $1}' | head -1
    else
        echo "unknown"
    fi
}

# Find next available port
find_available_port() {
    local start_port=$1
    local port=$start_port
    local max_tries=100
    
    while [[ $max_tries -gt 0 ]]; do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
        ((port++))
        ((max_tries--))
    done
    
    # Fallback
    echo "$start_port"
    return 1
}

# Check all ports for conflicts
check_port_conflicts() {
    header "Checking Port Availability"
    
    local conflicts_found=false
    local port_name port process
    
    echo "Checking required ports for conflicts..."
    echo ""
    
    for port_name in "${!DEFAULT_PORTS[@]}"; do
        port="${REMAPPED_PORTS[$port_name]:-${DEFAULT_PORTS[$port_name]}}"
        
        if is_port_in_use "$port"; then
            process=$(get_port_process "$port")
            warn "Port $port (${PORT_DESCRIPTIONS[$port_name]}) is in use by: $process"
            conflicts_found=true
        else
            success "Port $port (${PORT_DESCRIPTIONS[$port_name]}) is available"
        fi
    done
    
    echo ""
    
    if [[ "$conflicts_found" == "true" ]]; then
        return 1
    else
        success "All ports are available!"
        return 0
    fi
}

# Resolve port conflicts interactively
resolve_port_conflicts() {
    header "Resolving Port Conflicts"
    
    local port_name port new_port process suggestion
    
    for port_name in "${!DEFAULT_PORTS[@]}"; do
        port="${REMAPPED_PORTS[$port_name]:-${DEFAULT_PORTS[$port_name]}}"
        
        if is_port_in_use "$port"; then
            process=$(get_port_process "$port")
            echo ""
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            warn "Port $port (${PORT_DESCRIPTIONS[$port_name]}) is in use"
            echo "  Process: $process"
            echo ""
            
            # Find a suggestion
            suggestion=$(find_available_port "$((port + 1))")
            
            echo "Options:"
            echo "  1) Remap to different port (suggested: $suggestion)"
            echo "  2) Skip this service (disable port binding)"
            echo "  3) Keep as-is (will fail if port is still in use at startup)"
            echo ""
            
            read -r -p "Choose option [1/2/3] (default: 1): " choice
            choice=${choice:-1}
            
            case "$choice" in
                1)
                    new_port=$(ask_input "Enter new port" "$suggestion")
                    
                    # Check if the new port is also in use
                    while is_port_in_use "$new_port"; do
                        warn "Port $new_port is also in use!"
                        suggestion=$(find_available_port "$((new_port + 1))")
                        new_port=$(ask_input "Enter different port" "$suggestion")
                    done
                    
                    REMAPPED_PORTS[$port_name]="$new_port"
                    success "Remapped ${PORT_DESCRIPTIONS[$port_name]} to port $new_port"
                    ;;
                2)
                    REMAPPED_PORTS[$port_name]=""
                    warn "Disabled port binding for ${PORT_DESCRIPTIONS[$port_name]}"
                    ;;
                3)
                    info "Keeping port $port (may fail at startup)"
                    REMAPPED_PORTS[$port_name]="$port"
                    ;;
            esac
        fi
    done
    
    # Copy over any defaults that weren't conflicting
    for port_name in "${!DEFAULT_PORTS[@]}"; do
        if [[ -z "${REMAPPED_PORTS[$port_name]+x}" ]]; then
            REMAPPED_PORTS[$port_name]="${DEFAULT_PORTS[$port_name]}"
        fi
    done
}

# Get the configured port (or default)
get_port() {
    local port_name=$1
    echo "${REMAPPED_PORTS[$port_name]:-${DEFAULT_PORTS[$port_name]}}"
}

# Show help
show_help() {
    cat << EOF
Smart Hotel - Interactive Setup Script

Usage: $0 [OPTIONS]

Options:
  --auto        Fully automatic setup: configure, build, and start all services
  --defaults    Use default configuration (non-interactive, doesn't start services)
  --reset       Reset configuration (removes .env, regenerates secrets)
  --help        Show this help message

This script will:
  1. Generate secure secrets for all services
  2. Configure MQTT authentication (optional in interactive mode)
  3. Configure MQTT TLS encryption (optional in interactive mode)
  4. Configure InfluxDB initialization
  5. Prepare all services for first launch

Examples:
  ./setup.sh              # Interactive setup
  ./setup.sh --auto       # Automatic setup + build + start
  ./setup.sh --defaults   # Just generate config (no start)

EOF
}

# Prompt for yes/no
ask_yes_no() {
    local prompt="$1"
    local default="${2:-n}"
    local response
    
    if [[ "$default" == "y" ]]; then
        prompt="$prompt [Y/n]: "
    else
        prompt="$prompt [y/N]: "
    fi
    
    read -r -p "$prompt" response
    response=${response:-$default}
    
    [[ "$response" =~ ^[Yy]$ ]]
}

# Prompt for input with default
ask_input() {
    local prompt="$1"
    local default="$2"
    local response
    
    read -r -p "$prompt [$default]: " response
    echo "${response:-$default}"
}

# Configure MQTT authentication
configure_mqtt_auth() {
    header "MQTT Authentication"
    
    echo "MQTT authentication protects your message broker from unauthorized access."
    echo "This is recommended for production environments."
    echo ""
    
    if ask_yes_no "Enable MQTT authentication?" "y"; then
        MQTT_AUTH_ENABLED="true"
        
        # Get username
        MQTT_USER=$(ask_input "MQTT username" "smarthotel")
        
        # Get password or generate
        echo ""
        if ask_yes_no "Generate random MQTT password?" "y"; then
            MQTT_PASSWORD=$(generate_secret 24)
            success "Generated MQTT password"
        else
            read -r -s -p "Enter MQTT password: " MQTT_PASSWORD
            echo ""
        fi
        
        # Create password file
        info "Creating MQTT password file..."
        mkdir -p "$(dirname "$MOSQUITTO_PASSWD_FILE")"
        
        # Use mosquitto_passwd from docker if available
        if docker run --rm eclipse-mosquitto:latest mosquitto_passwd --help &>/dev/null 2>&1; then
            echo "$MQTT_PASSWORD" | docker run --rm -i \
                -v "$(dirname "$MOSQUITTO_PASSWD_FILE"):/mosquitto/config" \
                eclipse-mosquitto:latest \
                mosquitto_passwd -b -c /mosquitto/config/passwd "$MQTT_USER" /dev/stdin 2>/dev/null || \
            # Fallback: create file directly (less secure but works)
            echo "${MQTT_USER}:$(openssl passwd -6 "$MQTT_PASSWORD")" > "$MOSQUITTO_PASSWD_FILE"
        else
            # Create simple password file format
            echo "${MQTT_USER}:${MQTT_PASSWORD}" > "$MOSQUITTO_PASSWD_FILE"
            warn "Could not use mosquitto_passwd, created plain text file (less secure)"
        fi
        
        success "MQTT authentication configured"
    else
        MQTT_AUTH_ENABLED="false"
        MQTT_USER=""
        MQTT_PASSWORD=""
        info "MQTT authentication disabled (anonymous access)"
    fi
}

# Configure MQTT TLS
configure_mqtt_tls() {
    header "MQTT TLS Encryption"
    
    echo "TLS encryption secures MQTT communication between devices and the broker."
    echo "This requires SSL certificates (you can use self-signed for testing)."
    echo ""
    
    if ask_yes_no "Enable MQTT TLS?" "n"; then
        MQTT_TLS_ENABLED="true"
        
        mkdir -p "$TLS_DIR"
        
        # Check for existing certificates
        if [[ -f "$TLS_DIR/ca.crt" && -f "$TLS_DIR/server.crt" && -f "$TLS_DIR/server.key" ]]; then
            if ask_yes_no "Existing certificates found. Use them?" "y"; then
                success "Using existing TLS certificates"
                return
            fi
        fi
        
        if ask_yes_no "Generate self-signed certificates?" "y"; then
            info "Generating CA certificate..."
            openssl genrsa -out "$TLS_DIR/ca.key" 2048 2>/dev/null
            openssl req -new -x509 -days 3650 -key "$TLS_DIR/ca.key" \
                -out "$TLS_DIR/ca.crt" \
                -subj "/CN=Smart Hotel MQTT CA/O=Smart Hotel/C=US" 2>/dev/null
            
            info "Generating server certificate..."
            openssl genrsa -out "$TLS_DIR/server.key" 2048 2>/dev/null
            openssl req -new -key "$TLS_DIR/server.key" \
                -out "$TLS_DIR/server.csr" \
                -subj "/CN=mosquitto/O=Smart Hotel/C=US" 2>/dev/null
            openssl x509 -req -days 3650 \
                -in "$TLS_DIR/server.csr" \
                -CA "$TLS_DIR/ca.crt" \
                -CAkey "$TLS_DIR/ca.key" \
                -CAcreateserial \
                -out "$TLS_DIR/server.crt" 2>/dev/null
            
            # Set permissions
            chmod 600 "$TLS_DIR"/*.key
            chmod 644 "$TLS_DIR"/*.crt
            
            rm -f "$TLS_DIR/server.csr" "$TLS_DIR/ca.srl"
            
            success "Generated self-signed TLS certificates"
            warn "For production, replace with certificates from a trusted CA"
        else
            info "Please place your certificates in: $TLS_DIR"
            echo "  Required files: ca.crt, server.crt, server.key"
            MQTT_TLS_ENABLED="false"
        fi
    else
        MQTT_TLS_ENABLED="false"
        info "MQTT TLS disabled (unencrypted communication)"
    fi
}

# Update mosquitto.conf based on configuration
update_mosquitto_config() {
    header "Updating Mosquitto Configuration"
    
    # Backup original
    if [[ -f "$MOSQUITTO_CONF" && ! -f "${MOSQUITTO_CONF}.original" ]]; then
        cp "$MOSQUITTO_CONF" "${MOSQUITTO_CONF}.original"
    fi
    
    cat > "$MOSQUITTO_CONF" << 'EOF'
# Mosquitto MQTT Broker Configuration
# ============================================================================
# Auto-generated by setup.sh - Do not edit manually
# Run ./setup.sh to reconfigure

# Persistence settings
persistence true
persistence_location /mosquitto/data/

# Logging
log_dest file /mosquitto/log/mosquitto.log
log_type all
connection_messages true

EOF

    # Add authentication config
    if [[ "$MQTT_AUTH_ENABLED" == "true" ]]; then
        cat >> "$MOSQUITTO_CONF" << 'EOF'
# ============================================================================
# Authentication
# ============================================================================
allow_anonymous false
password_file /mosquitto/config/passwd

EOF
    else
        cat >> "$MOSQUITTO_CONF" << 'EOF'
# ============================================================================
# Authentication (disabled)
# ============================================================================
allow_anonymous true

EOF
    fi

    # Add listener config based on TLS
    if [[ "$MQTT_TLS_ENABLED" == "true" ]]; then
        cat >> "$MOSQUITTO_CONF" << 'EOF'
# ============================================================================
# TLS Listener (secure) - for external clients
# ============================================================================
listener 8883
cafile /mosquitto/config/certs/ca.crt
certfile /mosquitto/config/certs/server.crt
keyfile /mosquitto/config/certs/server.key
tls_version tlsv1.2

# Non-TLS listener - for internal Docker network (protected by Docker isolation)
listener 1883

# WebSocket listener with TLS
listener 9001
protocol websockets
cafile /mosquitto/config/certs/ca.crt
certfile /mosquitto/config/certs/server.crt
keyfile /mosquitto/config/certs/server.key
tls_version tlsv1.2

EOF
    else
        cat >> "$MOSQUITTO_CONF" << 'EOF'
# ============================================================================
# Listeners
# ============================================================================
# Default TCP listener
listener 1883

# WebSocket listener
listener 9001
protocol websockets

EOF
    fi

    success "Mosquitto configuration updated"
}

# Configure external URL
configure_urls() {
    header "Service URLs"
    
    echo "Configure the external hostname or FQDN for accessing services."
    echo ""
    echo "Examples:"
    echo "  - localhost (for local development)"
    echo "  - myserver.example.com (if you have a domain)"
    echo "  - 192.168.1.100 (direct IP access)"
    echo ""
    echo -e "${YELLOW}Note: If using a domain with a reverse proxy (nginx, traefik, caddy),${NC}"
    echo -e "${YELLOW}the proxy handles port mapping (e.g., https://dashboard.example.com → :8001)${NC}"
    echo ""
    
    EXTERNAL_HOST=$(ask_input "External hostname/FQDN" "localhost")
    
    # Determine protocol based on input
    if [[ "$EXTERNAL_HOST" == "localhost" || "$EXTERNAL_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        # localhost or IP - use http with ports
        GRAFANA_ROOT_URL="http://${EXTERNAL_HOST}:$(get_port GRAFANA_PORT)"
    else
        # Domain name - assume reverse proxy with https
        GRAFANA_ROOT_URL="https://${EXTERNAL_HOST}"
    fi
    
    DJANGO_ALLOWED_HOSTS="${EXTERNAL_HOST},localhost,127.0.0.1"
}

# Generate all secrets
generate_all_secrets() {
    header "Generating Secrets"
    
    info "Generating secure random secrets..."
    
    POSTGRES_PASSWORD=$(generate_secret 32)
    INFLUX_ADMIN_PASSWORD=$(generate_secret 32)
    INFLUX_TOKEN=$(generate_hex 32)
    DJANGO_SECRET_KEY=$(generate_secret 64)
    GRAFANA_ADMIN_PASSWORD=$(generate_secret 24)
    NODERED_CREDENTIAL_SECRET=$(generate_hex 32)
    KIOSK_SECRET_KEY=$(generate_secret 64)
    KIOSK_API_TOKEN=$(generate_hex 32)
    
    success "Generated all secrets"
}

# Write .env file
write_env_file() {
    header "Writing Configuration"
    
    cat > "$ENV_FILE" << EOF
# ============================================================================
# Smart Hotel Cloud Infrastructure - Environment Configuration
# ============================================================================
# Generated on: $(date -Iseconds)
# Generated by: setup.sh (interactive setup)
#
# IMPORTANT: Never commit this file to version control!
# ============================================================================

# ============================================================================
# TIMEZONE
# ============================================================================
TIMEZONE=UTC

# ============================================================================
# SESSION SETTINGS (7 days for hotel guests)
# ============================================================================
SESSION_COOKIE_AGE=604800

# ============================================================================
# POSTGRESQL - Main Application Database
# ============================================================================
POSTGRES_DB=smarthotel
POSTGRES_USER=smarthotel
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# ============================================================================
# INFLUXDB - Time-Series Database
# ============================================================================
INFLUX_PORT=$(get_port INFLUX_PORT)
INFLUX_ADMIN_USER=admin
INFLUX_ADMIN_PASSWORD=${INFLUX_ADMIN_PASSWORD}
INFLUX_ORG=smarthotel
INFLUX_BUCKET=sensors
INFLUX_RETENTION=0
INFLUX_TOKEN=${INFLUX_TOKEN}

# ============================================================================
# MQTT - Mosquitto Broker
# ============================================================================
MQTT_PORT=$(get_port MQTT_PORT)
MQTT_WS_PORT=$(get_port MQTT_WS_PORT)
MQTT_TLS_PORT=$(get_port MQTT_TLS_PORT)
MQTT_AUTH_ENABLED=${MQTT_AUTH_ENABLED:-false}
MQTT_TLS_ENABLED=${MQTT_TLS_ENABLED:-false}
MQTT_USER=${MQTT_USER:-}
MQTT_PASSWORD=${MQTT_PASSWORD:-}

# ============================================================================
# DJANGO DASHBOARD
# ============================================================================
DASHBOARD_PORT=$(get_port DASHBOARD_PORT)
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}

# ============================================================================
# GRAFANA
# ============================================================================
GRAFANA_PORT=$(get_port GRAFANA_PORT)
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
GRAFANA_ROOT_URL=${GRAFANA_ROOT_URL:-http://localhost:3000}

# ============================================================================
# KIOSK - Guest Registration Terminal
# ============================================================================
KIOSK_PORT=$(get_port KIOSK_PORT)
KIOSK_SECRET_KEY=${KIOSK_SECRET_KEY}
KIOSK_DEBUG=0
KIOSK_ALLOWED_HOSTS=*
KIOSK_API_TOKEN=${KIOSK_API_TOKEN}

# ============================================================================
# NODE-RED - Notification Gateway (Headless - no external port)
# ============================================================================
# No port exposed - accessed only internally via http://nodered:1880
NODERED_CREDENTIAL_SECRET=${NODERED_CREDENTIAL_SECRET}

# ============================================================================
# TWILIO - SMS Integration (via Node-RED)
# ============================================================================
# Get these from https://console.twilio.com/
# Leave empty to disable SMS functionality
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=

# ============================================================================
# TELEGRAM - Bot Notifications (Optional)
# ============================================================================
# Create a bot with @BotFather: https://t.me/botfather
# Get chat ID: https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ============================================================================
# SMTP - Email Configuration (Optional)
# ============================================================================
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=true
SMTP_FROM=noreply@example.com

EOF

    success ".env file created"
    
    # Update Grafana datasource with the generated token
    update_grafana_datasource
}

# Update Grafana datasource config with InfluxDB token
update_grafana_datasource() {
    local GRAFANA_DS_FILE="${SCRIPT_DIR}/config/grafana/provisioning/datasources/influxdb.yaml"
    
    if [[ -f "$GRAFANA_DS_FILE" ]]; then
        info "Updating Grafana InfluxDB datasource with token..."
        
        # Use sed to replace the token line
        if sed -i "s|token:.*|token: ${INFLUX_TOKEN}|" "$GRAFANA_DS_FILE" 2>/dev/null; then
            success "Grafana datasource updated with InfluxDB token"
        else
            warn "Could not update Grafana datasource - update manually in:"
            echo "    $GRAFANA_DS_FILE"
            echo "    Set: token: ${INFLUX_TOKEN}"
        fi
    else
        warn "Grafana datasource file not found: $GRAFANA_DS_FILE"
    fi
}

# Print summary
print_summary() {
    header "Setup Complete!"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${GREEN}Configuration Summary:${NC}"
    echo ""
    echo "  MQTT Authentication: $([ "$MQTT_AUTH_ENABLED" == "true" ] && echo "Enabled (user: $MQTT_USER)" || echo "Disabled")"
    echo "  MQTT TLS:            $([ "$MQTT_TLS_ENABLED" == "true" ] && echo "Enabled (port $(get_port MQTT_TLS_PORT))" || echo "Disabled")"
    echo ""
    
    # Show remapped ports if any
    local has_remaps=false
    for port_name in "${!REMAPPED_PORTS[@]}"; do
        if [[ "${REMAPPED_PORTS[$port_name]}" != "${DEFAULT_PORTS[$port_name]}" ]]; then
            has_remaps=true
            break
        fi
    done
    
    if [[ "$has_remaps" == "true" ]]; then
        echo -e "${YELLOW}Port Remapping:${NC}"
        for port_name in "${!REMAPPED_PORTS[@]}"; do
            if [[ "${REMAPPED_PORTS[$port_name]}" != "${DEFAULT_PORTS[$port_name]}" ]]; then
                if [[ -z "${REMAPPED_PORTS[$port_name]}" ]]; then
                    echo "  ${PORT_DESCRIPTIONS[$port_name]}: DISABLED"
                else
                    echo "  ${PORT_DESCRIPTIONS[$port_name]}: ${DEFAULT_PORTS[$port_name]} → ${REMAPPED_PORTS[$port_name]}"
                fi
            fi
        done
        echo ""
    fi
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${BOLD}Service Access:${NC}"
    echo ""
    echo "  Dashboard:     http://${EXTERNAL_HOST}:$(get_port DASHBOARD_PORT)"
    echo "                 Admin: admin / SmartHotel2026!"
    echo "  Grafana:       ${GRAFANA_ROOT_URL}"
    echo "  Kiosk:         http://${EXTERNAL_HOST}:$(get_port KIOSK_PORT)"
    echo "  InfluxDB:      http://${EXTERNAL_HOST}:$(get_port INFLUX_PORT)"
    echo ""
    echo "  Node-RED:      Internal only (http://nodered:1880)"
    echo ""
    if [[ "$EXTERNAL_HOST" != "localhost" && ! "$EXTERNAL_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo -e "${YELLOW}Note: Using domain '$EXTERNAL_HOST'. Ensure your reverse proxy${NC}"
        echo -e "${YELLOW}is configured to forward traffic to the correct ports.${NC}"
        echo ""
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [[ "$MQTT_AUTH_ENABLED" == "true" ]]; then
        echo -e "${YELLOW}MQTT Credentials (save these!):${NC}"
        echo "  Username: $MQTT_USER"
        echo "  Password: $MQTT_PASSWORD"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
    fi
    
    echo -e "${BOLD}Next Steps:${NC}"
    echo ""
    echo "  1. Start services:    ${CYAN}docker compose up -d${NC}"
    echo "  2. Wait for startup:  ${CYAN}docker compose logs -f${NC}"
    echo "  3. Configure Twilio/Telegram in .env if needed"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    success "Ready to launch! Run: docker compose up -d"
}

# Non-interactive defaults mode
run_defaults() {
    info "Running with defaults (non-interactive mode)..."
    
    MQTT_AUTH_ENABLED="false"
    MQTT_TLS_ENABLED="false"
    MQTT_USER=""
    MQTT_PASSWORD=""
    EXTERNAL_HOST="localhost"
    GRAFANA_ROOT_URL="http://localhost:3000"
    DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1"
    
    # Check for port conflicts in defaults mode
    if ! check_port_conflicts; then
        warn "Port conflicts detected in defaults mode!"
        warn "Using default ports anyway - you may need to resolve conflicts manually."
    fi
    
    # Initialize remapped ports with defaults
    for port_name in "${!DEFAULT_PORTS[@]}"; do
        REMAPPED_PORTS[$port_name]="${DEFAULT_PORTS[$port_name]}"
    done
    
    generate_all_secrets
    update_mosquitto_config
    write_env_file
    print_summary
}

# ============================================================================
# Shared Function: Build, Start, and Configure the Stack
# ============================================================================
build_start_and_configure() {
    # Hash MQTT password if authentication is enabled
    if [[ "$MQTT_AUTH_ENABLED" == "true" && -n "$MQTT_PASSWORD" ]]; then
        header "Configuring MQTT Authentication"
        info "Creating hashed MQTT password file..."
        
        # Use mosquitto container to hash the password
        if docker run --rm -v "${SCRIPT_DIR}/config/mosquitto:/data" eclipse-mosquitto \
            mosquitto_passwd -b -c /data/passwd "$MQTT_USER" "$MQTT_PASSWORD" 2>/dev/null; then
            success "MQTT password file created"
        else
            warn "Could not hash password - using plain text (less secure)"
        fi
    fi
    
    # Build and start the stack
    header "Building and Starting Services"
    
    info "Building containers (this may take a few minutes)..."
    if docker compose build --quiet 2>/dev/null; then
        success "Build complete"
    else
        warn "Build had warnings but continuing..."
    fi
    
    info "Starting services..."
    if docker compose up -d; then
        success "Services started"
    else
        error "Failed to start services!"
        exit 1
    fi
    
    # Wait for services to be healthy
    header "Waiting for Services"
    info "Waiting for services to become healthy..."
    
    local max_wait=120
    local waited=0
    local all_healthy=false
    
    while [[ $waited -lt $max_wait ]]; do
        local unhealthy=$(docker compose ps --format json 2>/dev/null | grep -c '"Health":"starting"' || echo "0")
        if [[ "$unhealthy" == "0" ]]; then
            all_healthy=true
            break
        fi
        echo -n "."
        sleep 5
        ((waited+=5))
    done
    echo ""
    
    if [[ "$all_healthy" == "true" ]]; then
        success "All services are healthy!"
    else
        warn "Some services may still be starting. Check with: docker compose ps"
    fi
    
    # Configure InfluxDB buckets
    header "Configuring InfluxDB"
    info "Creating InfluxDB buckets..."
    
    # Wait a bit for InfluxDB to be fully ready
    sleep 5
    
    docker compose exec -T influxdb sh -c '
        INFLUX_ORG="smarthotel"
        
        # Create additional buckets
        influx bucket create --name "face_events" --org "$INFLUX_ORG" --retention 604800s 2>/dev/null || true
        influx bucket create --name "system" --org "$INFLUX_ORG" --retention 2592000s 2>/dev/null || true
        influx bucket create --name "alerts" --org "$INFLUX_ORG" --retention 7776000s 2>/dev/null || true
    ' 2>/dev/null && success "InfluxDB buckets configured" || warn "Some InfluxDB buckets may already exist"
    
    # Run Django migrations and setup
    header "Configuring Dashboard"
    info "Running Django migrations..."
    docker compose exec -T dashboard python manage.py migrate --noinput 2>/dev/null && \
        success "Dashboard migrations complete" || warn "Dashboard migrations may need manual run"
    
    info "Creating initial rooms..."
    docker compose exec -T dashboard python manage.py shell -c "
from rooms.models import Room
for i in range(1, 6):
    Room.objects.get_or_create(
        room_number=str(100 + i),
        defaults={'name': f'Room {100+i}', 'floor': 1, 'capacity': 2, 'is_active': True}
    )
print('Rooms created')
" 2>/dev/null && success "Initial rooms created" || warn "Rooms may already exist"
    
    # Print final summary
    header "Setup Complete!"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}All services are running!${NC}"
    echo ""
    echo "Service URLs:"
    echo "  Dashboard:     http://${EXTERNAL_HOST}:$(get_port DASHBOARD_PORT)"
    echo "                 Login: admin / SmartHotel2026!"
    echo "  Grafana:       ${GRAFANA_ROOT_URL}"
    echo "  Kiosk:         http://${EXTERNAL_HOST}:$(get_port KIOSK_PORT)"
    echo "  InfluxDB:      http://${EXTERNAL_HOST}:$(get_port INFLUX_PORT)"
    echo ""
    echo "Internal-only services (not exposed externally):"
    echo "  Node-RED:      http://nodered:1880 (Docker internal only)"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [[ "$MQTT_AUTH_ENABLED" == "true" ]]; then
        echo ""
        echo "MQTT Credentials:"
        echo "  Username: ${MQTT_USER}"
        echo "  Password: ${MQTT_PASSWORD}"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
    
    echo ""
    success "Stack is running! Access the dashboard to get started."
}

# Fully automatic setup - configure, build, and start
run_auto() {
    info "Running fully automatic setup..."
    echo ""
    
    MQTT_AUTH_ENABLED="false"
    MQTT_TLS_ENABLED="false"
    MQTT_USER=""
    MQTT_PASSWORD=""
    
    # Use localhost by default (safe fallback, no public IP detection)
    EXTERNAL_HOST="localhost"
    GRAFANA_ROOT_URL="http://localhost:3000"
    DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1"
    
    # Auto-resolve port conflicts with tracking of already-allocated ports
    header "Checking Port Availability"
    declare -A ALLOCATED_PORTS  # Track ports we've already allocated
    
    for port_name in "${!DEFAULT_PORTS[@]}"; do
        local port="${DEFAULT_PORTS[$port_name]}"
        local new_port="$port"
        
        # Check if port is in use OR already allocated in this run
        while is_port_in_use "$new_port" || [[ -n "${ALLOCATED_PORTS[$new_port]}" ]]; do
            ((new_port++))
            if [[ $new_port -gt $((port + 100)) ]]; then
                error "Could not find available port for ${PORT_DESCRIPTIONS[$port_name]}"
                exit 1
            fi
        done
        
        if [[ "$new_port" != "$port" ]]; then
            warn "Port $port (${PORT_DESCRIPTIONS[$port_name]}) unavailable, remapping to $new_port"
        else
            success "Port $port (${PORT_DESCRIPTIONS[$port_name]}) is available"
        fi
        
        REMAPPED_PORTS[$port_name]="$new_port"
        ALLOCATED_PORTS[$new_port]="$port_name"
    done
    success "Port allocation complete"
    
    generate_all_secrets
    update_mosquitto_config
    write_env_file
    
    # Build, start, and configure the stack
    build_start_and_configure
}

# Reset configuration
reset_config() {
    warn "This will remove your current configuration!"
    
    if ask_yes_no "Are you sure you want to reset?" "n"; then
        rm -f "$ENV_FILE"
        rm -f "$MOSQUITTO_PASSWD_FILE"
        rm -rf "$TLS_DIR"
        
        if [[ -f "${MOSQUITTO_CONF}.original" ]]; then
            mv "${MOSQUITTO_CONF}.original" "$MOSQUITTO_CONF"
        fi
        
        success "Configuration reset complete"
        info "Run ./setup.sh to reconfigure"
    else
        info "Reset cancelled"
    fi
}

# Interactive setup
run_interactive() {
    # Check if already configured
    if [[ -f "$ENV_FILE" ]]; then
        warn "Existing configuration found!"
        echo ""
        if ! ask_yes_no "Reconfigure? (existing .env will be backed up)" "n"; then
            info "Setup cancelled"
            exit 0
        fi
        # Backup existing
        cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        info "Backed up existing .env"
    fi
    
    # Check for port conflicts first
    if ! check_port_conflicts; then
        echo ""
        if ask_yes_no "Would you like to resolve port conflicts interactively?" "y"; then
            resolve_port_conflicts
        else
            warn "Continuing with default ports - conflicts may cause startup failures"
            for port_name in "${!DEFAULT_PORTS[@]}"; do
                REMAPPED_PORTS[$port_name]="${DEFAULT_PORTS[$port_name]}"
            done
        fi
    else
        # No conflicts - initialize with defaults
        for port_name in "${!DEFAULT_PORTS[@]}"; do
            REMAPPED_PORTS[$port_name]="${DEFAULT_PORTS[$port_name]}"
        done
    fi
    
    configure_urls
    configure_mqtt_auth
    configure_mqtt_tls
    generate_all_secrets
    update_mosquitto_config
    write_env_file
    
    # Build, start, and configure the stack
    build_start_and_configure
}

# Main entry point
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║         Smart Hotel - Interactive Setup Wizard                  ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    
    check_dependencies
    
    case "${1:-}" in
        --help|-h)
            show_help
            exit 0
            ;;
        --auto)
            run_auto
            ;;
        --defaults)
            run_defaults
            ;;
        --reset)
            reset_config
            ;;
        *)
            run_interactive
            ;;
    esac
}

main "$@"
