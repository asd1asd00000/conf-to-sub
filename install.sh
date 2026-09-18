#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}=======================================================${NC}"
echo -e "${GREEN}          Gift Panel (conf-to-sub) Auto-Installer      ${NC}"
echo -e "${GREEN}=======================================================${NC}"

# 1. Install Prerequisites
echo -e "\n${YELLOW}[1/6] Installing system prerequisites...${NC}"
apt update -y
apt install -y python3 python3-pip python3-venv git curl wget

# 2. Clone or Update Repository
INSTALL_DIR="$HOME/conf-to-sub"
# ⚠️ IMPORTANT: Replace YOUR_GITHUB_USERNAME with your actual GitHub username!
REPO_URL="https://github.com/YOUR_GITHUB_USERNAME/conf-to-sub.git"

echo -e "\n${YELLOW}[2/6] Preparing project files...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory exists. Updating from GitHub..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Setup Virtual Environment & Dependencies
echo -e "\n${YELLOW}[3/6] Setting up Python environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create necessary directories
echo -e "\n${YELLOW}[4/6] Creating data directories...${NC}"
mkdir -p data
mkdir -p app/static
touch app/static/.gitkeep

# 5. Setup Systemd Service
echo -e "\n${YELLOW}[5/6] Configuring systemd service...${NC}"
SERVICE_NAME="conf-to-sub"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
ABSOLUTE_INSTALL_DIR=$(pwd)

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Gift Panel (conf-to-sub) FastAPI Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${ABSOLUTE_INSTALL_DIR}
ExecStart=${ABSOLUTE_INSTALL_DIR}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
Environment="PATH=${ABSOLUTE_INSTALL_DIR}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# 6. Check Service Status & Show Final Table
echo -e "\n${YELLOW}[6/6] Verifying service status...${NC}"
sleep 2
SERVICE_STATUS=$(systemctl is-active "$SERVICE_NAME")

# Fetch Public IP
SERVER_IP=$(curl -s --max-time 3 https://api.ipify.org)
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(curl -s --max-time 3 https://ifconfig.me)
fi
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(hostname -I | awk '{print $1}')
fi

# NOTE: 'clear' command removed so you can see all logs and errors above!

echo -e "\n${GREEN}=======================================================${NC}"
if [ "$SERVICE_STATUS" == "active" ]; then
    echo -e "${GREEN}                 INSTALLATION SUCCESSFUL               ${NC}"
else
    echo -e "${RED}              WARNING: SERVICE IS NOT RUNNING!          ${NC}"
    echo -e "${RED}     Check logs with: sudo journalctl -u conf-to-sub -n 50   ${NC}"
fi
echo -e "${GREEN}=======================================================${NC}"
echo -e "${BLUE}┌─────────────────────────────────────────────────────────────┐${NC}"
echo -e "${BLUE}│  🚀 Admin Panel URL : ${YELLOW}http://${SERVER_IP}:8000/admin/                  ${BLUE}│${NC}"
echo -e "${BLUE}│  📊 Service Status  : ${YELLOW}${SERVICE_STATUS}                                        ${BLUE}│${NC}"
echo -e "${BLUE}│  📜 View Live Logs  : ${YELLOW}sudo journalctl -u conf-to-sub -f                ${BLUE}│${NC}"
echo -e "${BLUE}│  🔄 Update Panel    : ${YELLOW}bash ~/conf-to-sub/update.sh                     ${BLUE}│${NC}"
echo -e "${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"
echo -e "${GREEN}=======================================================${NC}"
echo -e "${RED}⚠️  IMPORTANT: Ensure port 8000 is open in your firewall!    ${NC}"
echo -e "${GREEN}=======================================================${NC}"
