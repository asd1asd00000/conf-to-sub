#!/bin/bash

# Color codes for better output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}   Gift Panel (conf-to-sub) Installer    ${NC}"
echo -e "${GREEN}=========================================${NC}"

# 1. Install Prerequisites
echo -e "\n${YELLOW}[1/5] Installing system prerequisites...${NC}"
sudo apt update -y
sudo apt install -y python3 python3-pip python3-venv git curl

# 2. Determine Installation Directory
if [ -f "requirements.txt" ]; then
    INSTALL_DIR=$(pwd)
    echo -e "${GREEN}Found requirements.txt. Using current directory: ${INSTALL_DIR}${NC}"
else
    echo -e "${RED}Error: requirements.txt not found!${NC}"
    echo "Please run this script from the root of the 'conf-to-sub' repository."
    exit 1
fi

# 3. Setup Virtual Environment & Dependencies
echo -e "\n${YELLOW}[2/5] Setting up Python environment...${NC}"
cd "$INSTALL_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create necessary directories
echo -e "\n${YELLOW}[3/5] Creating data and static directories...${NC}"
mkdir -p data
mkdir -p app/static
touch app/static/.gitkeep # برای اینکه پوشه خالی در گیت ثبت شود

# 5. Setup Systemd Service
echo -e "\n${YELLOW}[4/5] Configuring systemd service...${NC}"
SERVICE_NAME="conf-to-sub"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Gift Panel (conf-to-sub) FastAPI Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
Environment="PATH=${INSTALL_DIR}/venv/bin"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

# 6. Final Output
SERVER_IP=$(hostname -I | awk '{print $1}')
echo -e "\n${GREEN}=========================================${NC}"
echo -e "${GREEN}          Installation Complete!           ${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "Admin Panel URL: ${YELLOW}http://${SERVER_IP}:8000/admin/${NC}"
echo -e "Service Status:  ${YELLOW}sudo systemctl status ${SERVICE_NAME}${NC}"
echo -e "View Live Logs:  ${YELLOW}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
echo -e "${GREEN}=========================================${NC}"
