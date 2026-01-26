#!/bin/bash

# Airtable Ticket Fetcher - Simple Runner
# This script loads credentials from credentials.env and runs the ticket fetcher

echo "🚀 Airtable Ticket Fetcher"
echo "========================="

# Check if credentials file exists
if [ ! -f "credentials.env" ]; then
    echo "❌ Error: credentials.env file not found"
    echo "Please create credentials.env with your Airtable credentials"
    exit 1
fi

# Load credentials from file
source credentials.env

# Validate required credentials
if [ -z "$AIRTABLE_TOKEN" ]; then
    echo "❌ Error: AIRTABLE_TOKEN not set in credentials.env"
    exit 1
fi

if [ -z "$AIRTABLE_BASE_ID" ]; then
    echo "❌ Error: AIRTABLE_BASE_ID not set in credentials.env"
    exit 1
fi

# Set defaults if not provided
AIRTABLE_TABLE_NAME=${AIRTABLE_TABLE_NAME:-"Tickets"}
AIRTABLE_TARGET_EMAIL=${AIRTABLE_TARGET_EMAIL:-"cw-testing@theforgelab.com"}
OUTPUT_DIRECTORY=${OUTPUT_DIRECTORY:-"output/airtable-tickets"}

echo "🔐 Using credentials from credentials.env"
echo "📋 Base ID: $AIRTABLE_BASE_ID"
echo "📊 Table: $AIRTABLE_TABLE_NAME"
echo "📧 Target email: $AIRTABLE_TARGET_EMAIL"
echo "📁 Output directory: $OUTPUT_DIRECTORY"
echo "========================="

# Activate virtual environment if it exists
if [ -d "src/venv" ]; then
    echo "🐍 Activating Python virtual environment..."
    source src/venv/bin/activate
fi

# Run the ticket fetcher
python src/fetch_airtable_tickets.py \
    --token "$AIRTABLE_TOKEN" \
    --base-id "$AIRTABLE_BASE_ID" \
    --table "$AIRTABLE_TABLE_NAME" \
    --email "$AIRTABLE_TARGET_EMAIL" \
    --output "$OUTPUT_DIRECTORY"

echo "✅ Ticket fetch completed!" 