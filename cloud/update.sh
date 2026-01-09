#!/usr/bin/env bash
# ============================================================================
# Smart Hotel - Update Script
# ============================================================================
# This script handles updates to the Smart Hotel infrastructure.
# It pulls new images, applies migrations, and restarts services gracefully.
#
# Usage:
#   ./update.sh              # Update all services
#   ./update.sh --pull-only  # Only pull new images (don't restart)
#   ./update.sh --service X  # Update specific service only
#   ./update.sh --help       # Show help
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }
header() { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${NC}\n"; }

# Show help
show_help() {
    cat << EOF
Smart Hotel - Update Script

Usage: $0 [OPTIONS]

Options:
  --pull-only         Only pull new images without restarting
  --service NAME      Update specific service only
  --no-backup         Skip database backup before update
  --help              Show this help

Services available for individual update:
  influxdb, postgres, dashboard, grafana, telegraf, mosquitto,
  nodered, kiosk, mrz-backend

Examples:
  $0                      # Full update
  $0 --service dashboard  # Update dashboard only
  $0 --pull-only          # Pull images without restart

EOF
}

# Check if services are running
check_running() {
    docker compose ps --format json 2>/dev/null | grep -q '"State":"running"'
}

# Backup function
backup_databases() {
    header "Backing Up Databases"
    
    local backup_dir="$SCRIPT_DIR/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # Backup PostgreSQL (main app)
    if docker compose ps postgres --format json 2>/dev/null | grep -q running; then
        info "Backing up PostgreSQL (smarthotel)..."
        docker compose exec -T postgres pg_dump -U smarthotel smarthotel > "$backup_dir/postgres_smarthotel.sql" 2>/dev/null || warn "PostgreSQL backup failed"
        success "PostgreSQL backup saved"
    fi
    
    # Backup InfluxDB metadata
    if docker compose ps influxdb --format json 2>/dev/null | grep -q running; then
        info "Backing up InfluxDB..."
        docker compose exec -T influxdb influx backup /tmp/influx_backup 2>/dev/null || warn "InfluxDB backup failed"
        docker compose cp influxdb:/tmp/influx_backup "$backup_dir/influxdb/" 2>/dev/null || true
        success "InfluxDB backup saved"
    fi
    
    success "Backups saved to: $backup_dir"
}

# Pull latest images
pull_images() {
    header "Pulling Latest Images"
    
    if [[ -n "$UPDATE_SERVICE" ]]; then
        info "Pulling image for: $UPDATE_SERVICE"
        docker compose pull "$UPDATE_SERVICE"
    else
        info "Pulling all images..."
        docker compose pull
    fi
    
    success "Images updated"
}

# Rebuild local images
rebuild_local() {
    header "Rebuilding Local Images"
    
    if [[ -n "$UPDATE_SERVICE" ]]; then
        if [[ "$UPDATE_SERVICE" == "dashboard" || "$UPDATE_SERVICE" == "kiosk" || "$UPDATE_SERVICE" == "mrz-backend" ]]; then
            info "Rebuilding: $UPDATE_SERVICE"
            docker compose build --no-cache "$UPDATE_SERVICE"
        fi
    else
        info "Rebuilding dashboard, kiosk, and mrz-backend..."
        docker compose build --no-cache dashboard kiosk mrz-backend
    fi
    
    success "Local images rebuilt"
}

# Apply migrations
apply_migrations() {
    header "Applying Migrations"
    
    # Dashboard migrations
    if [[ -z "$UPDATE_SERVICE" || "$UPDATE_SERVICE" == "dashboard" ]]; then
        if docker compose ps dashboard --format json 2>/dev/null | grep -q running; then
            info "Applying dashboard migrations..."
            docker compose exec -T dashboard python manage.py migrate --noinput 2>/dev/null || warn "Dashboard migrations failed"
            success "Dashboard migrations applied"
        fi
    fi
    
    # Kiosk uses SQLite, so migrations might be needed
    if [[ -z "$UPDATE_SERVICE" || "$UPDATE_SERVICE" == "kiosk" ]]; then
        if docker compose ps kiosk --format json 2>/dev/null | grep -q running; then
            info "Applying kiosk migrations..."
            docker compose exec -T kiosk python manage.py migrate --noinput 2>/dev/null || warn "Kiosk migrations failed"
            success "Kiosk migrations applied"
        fi
    fi
}

# Restart services gracefully
restart_services() {
    header "Restarting Services"
    
    if [[ -n "$UPDATE_SERVICE" ]]; then
        info "Restarting: $UPDATE_SERVICE"
        docker compose up -d --force-recreate "$UPDATE_SERVICE"
    else
        info "Restarting all services..."
        docker compose up -d --force-recreate
    fi
    
    success "Services restarted"
}

# Health check
health_check() {
    header "Health Check"
    
    local max_wait=120
    local waited=0
    local services_healthy=false
    
    info "Waiting for services to be healthy..."
    
    while [[ $waited -lt $max_wait ]]; do
        # Check if all services are running
        local unhealthy=$(docker compose ps --format json 2>/dev/null | grep -v running | grep -v exited || true)
        
        if [[ -z "$unhealthy" ]]; then
            services_healthy=true
            break
        fi
        
        sleep 5
        waited=$((waited + 5))
        echo -n "."
    done
    echo ""
    
    if $services_healthy; then
        success "All services are healthy"
    else
        warn "Some services may still be starting..."
        docker compose ps
    fi
}

# Cleanup old images
cleanup() {
    header "Cleanup"
    
    info "Removing dangling images..."
    docker image prune -f 2>/dev/null || true
    
    success "Cleanup complete"
}

# Full update process
full_update() {
    header "Smart Hotel Update"
    
    echo "This will update the Smart Hotel infrastructure."
    echo ""
    
    # Check if services are running
    if ! check_running; then
        warn "Services are not running. Starting fresh deployment..."
        docker compose up -d
        health_check
        exit 0
    fi
    
    # Backup databases
    if [[ "$NO_BACKUP" != "true" ]]; then
        backup_databases
    fi
    
    # Pull images
    pull_images
    
    # Rebuild local images
    rebuild_local
    
    # Restart services
    restart_services
    
    # Apply migrations
    apply_migrations
    
    # Health check
    health_check
    
    # Cleanup
    cleanup
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    success "Update complete!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

# Main
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║              Smart Hotel - Update Script                        ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    
    UPDATE_SERVICE=""
    PULL_ONLY=false
    NO_BACKUP=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --pull-only)
                PULL_ONLY=true
                shift
                ;;
            --service)
                UPDATE_SERVICE="$2"
                shift 2
                ;;
            --no-backup)
                NO_BACKUP=true
                shift
                ;;
            *)
                error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    if $PULL_ONLY; then
        pull_images
        success "Images pulled. Run 'docker compose up -d' to apply."
    else
        full_update
    fi
}

main "$@"
