#!/bin/bash

# Legacy setup script for Airtable ticket fetcher
# This script is deprecated. Use ./run.sh setup instead.

echo "⚠️  This script is deprecated. Please use './run.sh setup' instead."
echo "Setting up Airtable Ticket Fetcher..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed. Please install Python 3."
    exit 1
fi

cd src

# Install required packages
echo "Installing required Python packages..."
pip3 install -r requirements.txt

# Make the script executable
chmod +x fetch_airtable_tickets.py

echo "Setup complete!"
echo ""
echo "Usage:"
echo "./fetch_airtable_tickets.py --token YOUR_TOKEN --base-id YOUR_BASE_ID --table YOUR_TABLE_NAME"
echo ""
echo "Required information:"
echo "1. Personal Access Token from Airtable (https://airtable.com/developers/web/api/introduction)"
echo "2. Base ID from your Airtable URL (starts with 'app')"
echo "3. Table name (e.g., 'Tickets', 'Issues', etc.)"
echo ""
echo "Example:"
echo "./fetch_airtable_tickets.py --token patXXXXXXXXXXXXXX --base-id appXXXXXXXXXXXXXX --table Tickets" 