#!/bin/bash
# Run all Orchestrator tests
# Usage: ./run_tests.sh [test_file]

set -e
cd "$(dirname "$0")"

# Load environment
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Run specific test or all tests
if [ -n "$1" ]; then
    python3 -m pytest "tests/$1" -v
else
    python3 -m pytest tests/ -v
fi
