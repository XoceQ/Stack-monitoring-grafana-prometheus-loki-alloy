#!/bin/bash

# Utility script to manage the monitoring system
# Usage: ./monitor.sh [command]

set -e

# Output colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create .env from the template on first run, then load it
if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    echo -e "${YELLOW}Created .env from .env.example - review it and set GRAFANA_ADMIN_PASSWORD${NC}"
fi
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

# Host ports and credentials (same defaults as docker-compose.yml)
APP_URL="http://localhost:${APP_HOST_PORT:-8000}"
GRAFANA_URL="http://localhost:${GRAFANA_HOST_PORT:-3000}"
PROMETHEUS_URL="http://localhost:${PROMETHEUS_HOST_PORT:-9090}"
LOKI_URL="http://localhost:${LOKI_HOST_PORT:-3100}"
NODE_EXPORTER_URL="http://localhost:${NODE_EXPORTER_HOST_PORT:-9100}"
ALLOY_URL="http://localhost:${ALLOY_HOST_PORT:-12345}"

# Docker Compose command (v2 plugin preferred, v1 binary as fallback)
COMPOSE=""

# Show help
show_help() {
    echo -e "${BLUE}Monitoring system - Management script${NC}"
    echo ""
    echo "Usage: ./monitor.sh [command]"
    echo ""
    echo "Available commands:"
    echo -e "  ${GREEN}start${NC}       - Start all services"
    echo -e "  ${GREEN}stop${NC}        - Stop all services"
    echo -e "  ${GREEN}restart${NC}     - Restart all services"
    echo -e "  ${GREEN}status${NC}      - Show service status"
    echo -e "  ${GREEN}logs${NC}        - Show logs of all services"
    echo -e "  ${GREEN}build${NC}       - Rebuild images"
    echo -e "  ${GREEN}clean${NC}       - Remove containers and volumes"
    echo -e "  ${GREEN}test${NC}        - Generate test traffic"
    echo -e "  ${GREEN}logs-test${NC}   - Generate test logs"
    echo -e "  ${GREEN}loki-status${NC} - Check Loki status"
    echo -e "  ${GREEN}urls${NC}        - Show access URLs"
    echo -e "  ${GREEN}backup${NC}      - Create a data backup"
    echo -e "  ${GREEN}help${NC}        - Show this help"
    echo ""
    echo "Examples:"
    echo "  ./monitor.sh start"
    echo "  ./monitor.sh logs prometheus"
    echo "  ./monitor.sh test 100"
}

# Check that Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}Error: Docker is not running${NC}"
        exit 1
    fi
}

# Check that Docker Compose is available
check_docker_compose() {
    if docker compose version > /dev/null 2>&1; then
        COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE="docker-compose"
    else
        echo -e "${RED}Error: Docker Compose is not installed${NC}"
        exit 1
    fi
}

# Check that the sample application responds
check_app() {
    if ! curl -s "$APP_URL/health" > /dev/null; then
        echo -e "${RED}Error: the application is not responding at $APP_URL${NC}"
        return 1
    fi
}

# Start services
start_services() {
    echo -e "${BLUE}Starting monitoring system...${NC}"
    $COMPOSE up -d
    echo -e "${GREEN}✓ Services started successfully${NC}"
    sleep 5
    show_urls
}

# Stop services
stop_services() {
    echo -e "${BLUE}Stopping monitoring system...${NC}"
    $COMPOSE down
    echo -e "${GREEN}✓ Services stopped successfully${NC}"
}

# Restart services
restart_services() {
    echo -e "${BLUE}Restarting monitoring system...${NC}"
    $COMPOSE restart
    echo -e "${GREEN}✓ Services restarted successfully${NC}"
}

# Show status
show_status() {
    echo -e "${BLUE}Service status:${NC}"
    $COMPOSE ps
}

# Show logs
show_logs() {
    if [ -n "$2" ]; then
        echo -e "${BLUE}Logs for service $2:${NC}"
        $COMPOSE logs -f "$2"
    else
        echo -e "${BLUE}Logs for all services:${NC}"
        $COMPOSE logs -f
    fi
}

# Rebuild images
build_images() {
    echo -e "${BLUE}Rebuilding images...${NC}"
    $COMPOSE build --no-cache
    echo -e "${GREEN}✓ Images rebuilt successfully${NC}"
}

# Clean up the system
clean_system() {
    echo -e "${YELLOW}Are you sure you want to remove all containers and volumes? (y/N)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${BLUE}Cleaning up system...${NC}"
        $COMPOSE down -v --remove-orphans
        docker system prune -f
        echo -e "${GREEN}✓ System cleaned up successfully${NC}"
    else
        echo -e "${YELLOW}Operation cancelled${NC}"
    fi
}

# Generate test traffic
generate_test_traffic() {
    local requests=${2:-30}
    echo -e "${BLUE}Sending $requests test requests to the API...${NC}"

    check_app || return 1

    echo "Sending requests..."
    for ((i=1; i<=requests; i++)); do
        # Hit different API endpoints
        case $((i % 5)) in
            0) curl -s "$APP_URL/" > /dev/null ;;
            1) curl -s "$APP_URL/health" > /dev/null ;;
            2) curl -s "$APP_URL/users" > /dev/null ;;
            3) curl -s "$APP_URL/data" > /dev/null ;;
            4) curl -s -X POST "$APP_URL/process" > /dev/null ;;
        esac

        # Show progress every 10 requests
        if ((i % 10 == 0)); then
            echo -ne "\rProgress: $i/$requests requests"
        fi

        sleep 0.2
    done
    echo ""
    echo -e "${GREEN}✓ $requests requests sent to the API endpoints${NC}"
}

# Generate test logs
generate_test_logs() {
    echo -e "${BLUE}Generating test logs...${NC}"

    check_app || return 1

    curl -s "$APP_URL/logs" > /dev/null

    echo -e "${GREEN}✓ Test logs generated${NC}"
    echo -e "${YELLOW}Note: logs will show up in Loki after a few seconds${NC}"
}

# Check Loki status
check_loki_status() {
    echo -e "${BLUE}Checking Loki status...${NC}"

    # Is Loki running?
    if [ -z "$($COMPOSE ps --status running -q loki 2>/dev/null)" ]; then
        echo -e "${RED}✗ Loki is not running${NC}"
        return 1
    fi

    echo -e "${GREEN}✓ Loki is running${NC}"

    # Readiness endpoint
    if curl -s "$LOKI_URL/ready" > /dev/null; then
        echo -e "${GREEN}✓ Loki is responding${NC}"
    else
        echo -e "${YELLOW}⚠ Loki is not responding on its readiness endpoint${NC}"
    fi

    # Is the log collector (Grafana Agent / Alloy) running?
    if [ -n "$($COMPOSE ps --status running -q alloy 2>/dev/null)" ]; then
        echo -e "${GREEN}✓ Alloy is running${NC}"
    else
        echo -e "${RED}✗ Alloy is not running${NC}"
    fi

    echo ""
    echo -e "${BLUE}Viewing logs in Grafana:${NC}"
    echo "1. Go to $GRAFANA_URL"
    echo "2. Select 'Explore'"
    echo "3. Choose the 'Loki' datasource"
    echo "4. Use the query: {job=\"flask-app-logs\"}"
}

# Show URLs
show_urls() {
    echo -e "${BLUE}System access URLs:${NC}"
    echo ""
    echo -e "${GREEN}Grafana:${NC}         $GRAFANA_URL"
    echo -e "   ${YELLOW}User:${NC}          ${GRAFANA_ADMIN_USER:-admin}"
    echo -e "   ${YELLOW}Password:${NC}      see GRAFANA_ADMIN_PASSWORD in .env"
    echo ""
    echo -e "${GREEN}Prometheus:${NC}      $PROMETHEUS_URL"
    echo -e "${GREEN}Loki:${NC}            $LOKI_URL"
    echo -e "${GREEN}Alloy:${NC}           $ALLOY_URL"
    echo -e "${GREEN}Node Exporter:${NC}   $NODE_EXPORTER_URL"
    echo -e "${GREEN}Application:${NC}     $APP_URL"
    echo ""
    echo -e "API endpoints:"
    echo -e "   ${BLUE}Home:${NC}            $APP_URL/"
    echo -e "   ${BLUE}Health:${NC}          $APP_URL/health"
    echo -e "   ${BLUE}Users:${NC}           $APP_URL/users"
    echo -e "   ${BLUE}Data:${NC}            $APP_URL/data"
    echo -e "   ${BLUE}Process:${NC}         $APP_URL/process"
    echo -e "   ${BLUE}Test logs:${NC}       $APP_URL/logs"
    echo -e "   ${BLUE}Metrics:${NC}         $APP_URL/metrics"
}

# Create backup
create_backup() {
    local backup_dir
    backup_dir="backup-$(date +%Y%m%d-%H%M%S)"
    echo -e "${BLUE}Creating backup in $backup_dir...${NC}"

    mkdir -p "$backup_dir"

    # Back up configuration
    cp -r prometheus "$backup_dir/"
    cp -r grafana "$backup_dir/"
    cp -r loki "$backup_dir/" 2>/dev/null || true
    cp -r alloy "$backup_dir/" 2>/dev/null || true
    cp docker-compose.yml .env.example "$backup_dir/"

    # Back up container data (if running)
    if [ -n "$($COMPOSE ps --status running -q 2>/dev/null)" ]; then
        echo "Backing up Grafana data..."
        docker cp grafana:/var/lib/grafana "$backup_dir/grafana-data" 2>/dev/null || true

        echo "Backing up Prometheus data..."
        docker cp prometheus:/prometheus "$backup_dir/prometheus-data" 2>/dev/null || true

        echo "Backing up Loki data..."
        docker cp loki:/loki "$backup_dir/loki-data" 2>/dev/null || true
    fi

    echo -e "${GREEN}✓ Backup created in $backup_dir${NC}"
}

# Main entry point
main() {
    # Check dependencies
    check_docker
    check_docker_compose

    case "${1:-help}" in
        "start")
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "status"|"ps")
            show_status
            ;;
        "logs")
            show_logs "$@"
            ;;
        "build")
            build_images
            ;;
        "clean")
            clean_system
            ;;
        "test")
            generate_test_traffic "$@"
            ;;
        "logs-test")
            generate_test_logs
            ;;
        "loki-status")
            check_loki_status
            ;;
        "urls")
            show_urls
            ;;
        "backup")
            create_backup
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            echo -e "${RED}Unknown command: $1${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main with all arguments
main "$@"
