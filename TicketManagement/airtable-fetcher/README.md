# Airtable Ticket Fetcher

A containerized application to fetch tickets assigned to `cw-testing@theforgelab.com` from Airtable and organize them by creation date.

## 📁 Project Structure

```
airtable-fetcher/
├── src/                          # Source code
│   ├── fetch_airtable_tickets.py # Main Python script
│   └── requirements.txt          # Python dependencies
├── docker/                       # Docker configuration
│   ├── Dockerfile               # Container definition
│   ├── docker-compose.yml       # Multi-container setup
│   └── env.example              # Environment variables template
├── config/                       # Configuration files
│   └── airtable_config.json.example
├── docs/                         # Documentation
│   └── README_AIRTABLE.md       # Detailed usage guide
├── output/                       # Output directory (created automatically)
├── run.sh                       # Main execution script
├── setup_and_run.sh            # Legacy setup script
└── README.md                    # This file
```

## 🚀 Quick Start

### Option 1: Docker (Recommended)

1. **Build and run with Docker:**
   ```bash
   ./run.sh build
   ./run.sh docker --token YOUR_TOKEN --base-id YOUR_BASE_ID --table YOUR_TABLE_NAME
   ```

### Option 2: Native Python

1. **Setup native environment:**
   ```bash
   ./run.sh setup
   ```

2. **Run natively:**
   ```bash
   ./run.sh native --token YOUR_TOKEN --base-id YOUR_BASE_ID --table YOUR_TABLE_NAME
   ```

## 🐳 Docker Environment

This setup uses a **separate Docker network** (`airtable-network`) to avoid conflicts with the existing Magento Docker environment in `cw/docker-setup/`.

### Key Differences from Magento Docker:
- **Network**: `airtable-network` (vs `magento`)
- **Ports**: 9000 for Portainer (vs 80, 443, 3306 for Magento)
- **Services**: Lightweight Python container + optional Portainer
- **Isolation**: Completely separate from Magento containers

### Available Services:
- **airtable-fetcher**: Main Python application
- **portainer** (optional): Web UI for Docker management at `http://localhost:9000`

## 📋 Usage Examples

### Basic Usage
```bash
# Using Docker
./run.sh docker --token patXXXXXXXXXXXXXX --base-id appXXXXXXXXXXXXXX --table Tickets

# Using native Python
./run.sh native --token patXXXXXXXXXXXXXX --base-id appXXXXXXXXXXXXXX --table Tickets
```

### Advanced Usage
```bash
# Custom email and output directory
./run.sh docker \
  --token patXXXXXXXXXXXXXX \
  --base-id appXXXXXXXXXXXXXX \
  --table Issues \
  --email different@email.com \
  --output custom-tickets
```

### Management Commands
```bash
# Build Docker image
./run.sh build

# Setup native Python environment
./run.sh setup

# Clean up Docker resources
./run.sh clean
```

## 🔧 Configuration

### Method 1: Command Line Arguments
Pass credentials directly as shown in the examples above.

### Method 2: Environment Variables (Docker)
1. Copy the environment template:
   ```bash
   cp docker/env.example docker/.env
   ```

2. Edit `docker/.env` with your credentials:
   ```env
   AIRTABLE_TOKEN=your_token_here
   AIRTABLE_BASE_ID=your_base_id_here
   AIRTABLE_TABLE_NAME=Tickets
   ```

### Method 3: Configuration File
1. Copy and customize the config file:
   ```bash
   cp config/airtable_config.json.example config/airtable_config.json
   ```

## 📤 Output Structure

The application creates organized folders:

```
output/
├── 2024-01-15/
│   ├── recXXXXXX_Ticket_Title.json
│   ├── recXXXXXX_Ticket_Title.txt
│   └── ...
├── 2024-01-16/
│   └── ...
└── fetch_summary.txt
```

## 🛠 Development

### Running Interactively
To run the container interactively for development:

1. Edit `docker/docker-compose.yml` and uncomment these lines:
   ```yaml
   command: tail -f /dev/null
   stdin_open: true
   tty: true
   ```

2. Start the container:
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   docker exec -it airtable-fetcher bash
   ```

### Testing
```bash
# Test Docker build
./run.sh build

# Test with help command
./run.sh docker --help
./run.sh native --help
```

## 🔍 Troubleshooting

### Docker Issues
- **Port conflicts**: Portainer uses port 9000 (different from Magento's 80/443)
- **Network conflicts**: Uses `airtable-network` (separate from Magento's `magento` network)
- **Permission issues**: Container runs as non-root user `airtable`

### Common Problems
1. **"Docker command not found"**: Install Docker Desktop
2. **"Permission denied"**: Run `chmod +x run.sh`
3. **"Module not found"**: Run `./run.sh setup` for native or `./run.sh build` for Docker
4. **"Invalid token"**: Check your Airtable Personal Access Token

### Logs
```bash
# Docker logs
docker-compose -f docker/docker-compose.yml logs -f

# Container inspection
docker exec -it airtable-fetcher bash
```

## 🔐 Security

- Container runs as non-root user
- No sensitive data stored in images
- Environment variables for credentials
- Isolated network from Magento environment

## 📖 Additional Documentation

- See `docs/README_AIRTABLE.md` for detailed Airtable API information
- Check `config/airtable_config.json.example` for configuration options
- Review `docker/env.example` for environment variable setup 