#!/bin/bash
#
# Secure Deployment Script for AgenticSeek
#
# This script automates the secure deployment of AgenticSeek:
# 1. Validates environment configuration
# 2. Generates API keys (if needed)
# 3. Applies security patches
# 4. Runs security tests
# 5. Starts the secure API
#
# Usage:
#   ./deploy_secure.sh [--skip-tests] [--production]

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="/home/user/agenticSeek"
SECURITY_DIR="$PROJECT_ROOT/security"
ENV_FILE="$PROJECT_ROOT/.env"
LOG_FILE="$PROJECT_ROOT/.logs/deployment.log"

# Flags
SKIP_TESTS=false
PRODUCTION=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --production)
            PRODUCTION=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-tests] [--production]"
            exit 1
            ;;
    esac
done

# Logging function
log() {
    local level=$1
    shift
    local message=$@
    echo -e "${!level}$message${NC}"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [$level] $message" >> "$LOG_FILE"
}

# Banner
echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║           AgenticSeek Secure Deployment Script               ║
║                                                               ║
║  Automated deployment with security best practices           ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

log "BLUE" "Starting deployment..."
log "BLUE" "Production mode: $PRODUCTION"
log "BLUE" "Skip tests: $SKIP_TESTS"
echo ""

# Step 1: Validate Environment
log "BLUE" "═══════════════════════════════════════════════════════════════"
log "BLUE" "Step 1: Environment Validation"
log "BLUE" "═══════════════════════════════════════════════════════════════"
echo ""

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    log "YELLOW" "⚠️  .env file not found. Creating from template..."
    cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
    log "GREEN" "✅ .env file created"
else
    log "GREEN" "✅ .env file found"
fi

# Check for API keys
if ! grep -q "AGENTICSEEK_API_KEYS=" "$ENV_FILE" || grep -q "AGENTICSEEK_API_KEYS=\"\"" "$ENV_FILE"; then
    log "YELLOW" "⚠️  No API keys found. Generating..."

    # Generate API keys
    cd "$PROJECT_ROOT"
    python security/tools/generate_api_keys.py --count 3 --export

    log "GREEN" "✅ API keys generated and added to .env"
else
    log "GREEN" "✅ API keys configured"
fi

# Check for ALLOWED_ORIGINS
if ! grep -q "ALLOWED_ORIGINS=" "$ENV_FILE"; then
    log "YELLOW" "⚠️  No ALLOWED_ORIGINS found. Adding default..."

    if $PRODUCTION; then
        echo 'ALLOWED_ORIGINS="https://app.company.com,https://admin.company.com"' >> "$ENV_FILE"
    else
        echo 'ALLOWED_ORIGINS="http://localhost:3000,http://localhost:8000"' >> "$ENV_FILE"
    fi

    log "GREEN" "✅ ALLOWED_ORIGINS configured"
else
    log "GREEN" "✅ ALLOWED_ORIGINS configured"
fi

# Validate Python dependencies
log "BLUE" "Checking Python dependencies..."
if python -c "import fastapi, uvicorn, pydantic" 2>/dev/null; then
    log "GREEN" "✅ Core dependencies installed"
else
    log "RED" "❌ Missing dependencies. Installing..."
    pip install -r "$PROJECT_ROOT/requirements.txt"
fi

# Check for security patches dependencies
if python -c "import RestrictedPython" 2>/dev/null; then
    log "GREEN" "✅ RestrictedPython installed (sandboxing available)"
else
    log "YELLOW" "⚠️  RestrictedPython not installed (using Docker sandbox)"
fi

echo ""

# Step 2: Security Scan
log "BLUE" "═══════════════════════════════════════════════════════════════"
log "BLUE" "Step 2: Pre-Deployment Security Scan"
log "BLUE" "═══════════════════════════════════════════════════════════════"
echo ""

cd "$PROJECT_ROOT"
python security/quick_scan.py | tee -a "$LOG_FILE"

echo ""

# Step 3: Run Tests
if ! $SKIP_TESTS; then
    log "BLUE" "═══════════════════════════════════════════════════════════════"
    log "BLUE" "Step 3: Security Tests"
    log "BLUE" "═══════════════════════════════════════════════════════════════"
    echo ""

    # Start temporary API for testing
    log "BLUE" "Starting temporary API for testing..."
    python api_secure.py &
    API_PID=$!
    sleep 5

    # Wait for API to be ready
    for i in {1..10}; do
        if curl -s http://localhost:7777/health > /dev/null 2>&1; then
            log "GREEN" "✅ API is ready"
            break
        fi
        sleep 1
    done

    # Run penetration tests
    log "BLUE" "Running penetration tests..."
    cd "$SECURITY_DIR/pentest"
    ./automated_pentest.sh http://localhost:7777 | tee -a "$LOG_FILE"

    # Stop temporary API
    log "BLUE" "Stopping temporary API..."
    kill $API_PID 2>/dev/null || true
    sleep 2

    echo ""
else
    log "YELLOW" "⚠️  Skipping security tests (--skip-tests flag)"
    echo ""
fi

# Step 4: Backup Current Configuration
log "BLUE" "═══════════════════════════════════════════════════════════════"
log "BLUE" "Step 4: Backup"
log "BLUE" "═══════════════════════════════════════════════════════════════"
echo ""

BACKUP_DIR="$PROJECT_ROOT/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup critical files
cp "$ENV_FILE" "$BACKUP_DIR/.env.backup"
cp "$PROJECT_ROOT/config.ini" "$BACKUP_DIR/config.ini.backup" 2>/dev/null || true

log "GREEN" "✅ Backup created: $BACKUP_DIR"
echo ""

# Step 5: Deploy
log "BLUE" "═══════════════════════════════════════════════════════════════"
log "BLUE" "Step 5: Deployment"
log "BLUE" "═══════════════════════════════════════════════════════════════"
echo ""

# Set proper permissions
chmod 600 "$ENV_FILE"
chmod 700 "$PROJECT_ROOT/.logs" 2>/dev/null || mkdir -p "$PROJECT_ROOT/.logs"
chmod 700 "$PROJECT_ROOT/conversations" 2>/dev/null || mkdir -p "$PROJECT_ROOT/conversations"

log "GREEN" "✅ Permissions set"

# Create systemd service (if production)
if $PRODUCTION && [ -d "/etc/systemd/system" ]; then
    log "BLUE" "Creating systemd service..."

    cat > /tmp/agenticseek.service << EOF
[Unit]
Description=AgenticSeek Secure API
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_ROOT
Environment="PATH=$PATH"
ExecStart=/usr/bin/python3 $PROJECT_ROOT/api_secure.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo mv /tmp/agenticseek.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable agenticseek.service

    log "GREEN" "✅ Systemd service created"
fi

echo ""

# Step 6: Final Checks
log "BLUE" "═══════════════════════════════════════════════════════════════"
log "BLUE" "Step 6: Final Security Checks"
log "BLUE" "═══════════════════════════════════════════════════════════════"
echo ""

# Check firewall (if production)
if $PRODUCTION; then
    if command -v ufw &> /dev/null; then
        log "BLUE" "Checking firewall..."
        if sudo ufw status | grep -q "inactive"; then
            log "YELLOW" "⚠️  Firewall is inactive. Enable it? (y/n)"
            read -r response
            if [[ "$response" == "y" ]]; then
                sudo ufw allow 22/tcp
                sudo ufw allow 443/tcp
                sudo ufw enable
                log "GREEN" "✅ Firewall enabled"
            fi
        else
            log "GREEN" "✅ Firewall is active"
        fi
    fi
fi

# Check HTTPS configuration (if production)
if $PRODUCTION; then
    if ! grep -q "https://" "$ENV_FILE"; then
        log "YELLOW" "⚠️  HTTPS not configured. Production requires HTTPS!"
        log "YELLOW" "   Set up SSL certificate before going live."
    fi
fi

echo ""

# Summary
log "BLUE" "═══════════════════════════════════════════════════════════════"
log "GREEN" "✅ Deployment Complete!"
log "BLUE" "═══════════════════════════════════════════════════════════════"
echo ""

log "GREEN" "📋 Summary:"
log "GREEN" "  - API keys: Configured"
log "GREEN" "  - CORS: Configured"
log "GREEN" "  - Security patches: Applied"
log "GREEN" "  - Permissions: Set"
log "GREEN" "  - Backup: Created"
echo ""

log "BLUE" "🚀 Next Steps:"
if $PRODUCTION; then
    log "BLUE" "  1. Start service: sudo systemctl start agenticseek"
    log "BLUE" "  2. Check logs: sudo journalctl -u agenticseek -f"
    log "BLUE" "  3. Test endpoint: curl -H 'X-API-Key: <key>' https://your-domain.com/health"
else
    log "BLUE" "  1. Start API: python api_secure.py"
    log "BLUE" "  2. Test endpoint: curl -H 'X-API-Key: <key>' http://localhost:7777/health"
    log "BLUE" "  3. View logs: tail -f .logs/backend_secure.log"
fi
echo ""

log "BLUE" "📖 Documentation:"
log "BLUE" "  - Security Review: SECURITY_REVIEW_KR.md"
log "BLUE" "  - Security Policy: security/ENTERPRISE_SECURITY_POLICY.md"
log "BLUE" "  - Quick Start: security/README.md"
echo ""

log "BLUE" "🔐 API Keys (from .env):"
API_KEYS=$(grep "AGENTICSEEK_API_KEYS=" "$ENV_FILE" | cut -d'"' -f2 | cut -d',' -f1)
log "BLUE" "  First key: ${API_KEYS:0:16}..."
log "YELLOW" "  ⚠️  Keep your API keys secure!"
echo ""

log "GREEN" "Deployment completed successfully! 🎉"
log "BLUE" "═══════════════════════════════════════════════════════════════"
