#!/bin/bash

# Airtable Ticket Fetcher - Main Run Script
# This script can run the fetcher either natively or via Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    echo "Usage: $0 [OPTIONS] COMMAND"
    echo ""
    echo "Commands:"
    echo "  native    Run using local Python installation"
    echo "  docker    Run using Docker container"
    echo "  build     Build Docker image"
    echo "  setup     Setup native environment"
    echo "  clean     Clean up Docker resources"
    echo ""
    echo "Options:"
    echo "  --token TOKEN        Airtable Personal Access Token"
    echo "  --base-id ID         Airtable Base ID"
    echo "  --table TABLE        Table name"
    echo "  --email EMAIL        Target email (default: cw-testing@theforgelab.com)"
    echo "  --output DIR         Output directory"
    echo "  --help               Show this help message"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Docker is not installed or not running${NC}"
        exit 1
    fi
}

check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Python 3 is not installed${NC}"
        exit 1
    fi
}

setup_native() {
    echo -e "${BLUE}Setting up native Python environment...${NC}"
    check_python
    
    cd src
    if [ ! -f requirements.txt ]; then
        echo -e "${RED}requirements.txt not found in src/ directory${NC}"
        exit 1
    fi
    
    echo "Installing Python dependencies..."
    pip3 install -r requirements.txt
    chmod +x fetch_airtable_tickets.py
    echo -e "${GREEN}Native environment setup complete!${NC}"
}

build_docker() {
    echo -e "${BLUE}Building Docker image...${NC}"
    check_docker
    
    cd docker
    docker-compose build
    echo -e "${GREEN}Docker image built successfully!${NC}"
}

run_native() {
    echo -e "${BLUE}Running with native Python...${NC}"
    check_python
    
    cd src
    if [ ! -f fetch_airtable_tickets.py ]; then
        echo -e "${RED}fetch_airtable_tickets.py not found in src/ directory${NC}"
        exit 1
    fi
    
    # Pass all arguments to the Python script
    python3 fetch_airtable_tickets.py "$@"
}

run_docker() {
    echo -e "${BLUE}Running with Docker...${NC}"
    check_docker
    
    cd docker
    
    # Build if image doesn't exist
    if ! docker images | grep -q "airtable-fetcher"; then
        echo "Docker image not found. Building..."
        docker-compose build
    fi
    
    # Run the container with passed arguments
    docker-compose run --rm airtable-fetcher python fetch_airtable_tickets.py "$@"
}

clean_docker() {
    echo -e "${BLUE}Cleaning up Docker resources...${NC}"
    check_docker
    
    cd docker
    docker-compose down --volumes --remove-orphans
    docker system prune -f
    echo -e "${GREEN}Docker cleanup complete!${NC}"
}

# Parse command line arguments
COMMAND=""
ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        native|docker|build|setup|clean)
            if [ -z "$COMMAND" ]; then
                COMMAND="$1"
            else
                ARGS+=("$1")
            fi
            shift
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

# Execute command
case $COMMAND in
    native)
        run_native "${ARGS[@]}"
        ;;
    docker)
        run_docker "${ARGS[@]}"
        ;;
    build)
        build_docker
        ;;
    setup)
        setup_native
        ;;
    clean)
        clean_docker
        ;;
    "")
        echo -e "${RED}No command specified${NC}"
        print_usage
        exit 1
        ;;
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        print_usage
        exit 1
        ;;
esac 