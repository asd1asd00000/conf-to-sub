#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="$HOME/conf-to-sub"

# تنظیم میرور برای pip (مخصوص سرورهای ایران)
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

echo -e "${GREEN}=======================================================${NC}"
echo -e "${GREEN}          Gift Panel (conf-to-sub) Auto-Installer      ${NC}"
echo -e "${GREEN}          (Optimized for Iranian Servers)              ${NC}"
echo -e "${GREEN}=======================================================${NC}"

# 1. Install Prerequisites
echo -e "\n${YELLOW}[1/6] Installing system prerequisites...${NC}"
apt update -y
apt install -y python3 python3-pip python3-venv git curl wget

# 2. Prepare Project Files
echo -e "\n${YELLOW}[2/6] Preparing project files...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    echo -e "${GREEN}✓ Directory exists. Updating from GitHub...${NC}"
    cd "$INSTALL_DIR" || exit
    git pull origin main
else
    echo -e "${YELLOW}Repository not found. Please provide your GitHub username.${NC}"
    read -p "Enter your GitHub username: " GITHUB_USER
    
    if [ -z "$GITHUB_USER" ]; then
        echo -e "${RED}❌ Error: GitHub username cannot be empty.${NC}"
        exit 1
    fi
    
    REPO_URL="https://github.com/${GITHUB_USER}/conf-to-sub.git"
    echo -e "${GREEN}Cloning from: ${REPO_URL}${NC}"
    
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR" || exit
fi

# 3. Setup Virtual Environment & Dependencies (with China Mirror)
echo -e "\n${YELLOW}[3/6] Setting up Python environment (using China mirror)...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
# نصب requests به صورت جداگانه
echo -e "${BLUE}→ Installing requests for health checker...${NC}"
pip install requests -i "$PIP_MIRROR" --trusted-host pypi.tuna.tsinghua.edu.cn

# ارتقای pip با میرور چینی
echo -e "${BLUE}→ Upgrading pip via mirror...${NC}"
pip install --upgrade pip -i "$PIP_MIRROR" --trusted-host pypi.tuna.tsinghua.edu.cn

# نصب پکیج‌ها با میرور چینی
echo -e "${BLUE}→ Installing dependencies via mirror...${NC}"
pip install -r requirements.txt -i "$PIP_MIRROR" --trusted-host pypi.tuna.tsinghua.edu.cn
# نصب پکیج‌های اضافی که ممکن است در requirements نباشند
pip install qrcode==7.4.2 -i "$PIP_MIRROR" --trusted-host pypi.tuna.tsinghua.edu.cn

# بررسی موفقیت نصب
if [ ! -f "venv/bin/uvicorn" ]; then
    echo -e "${RED}❌ Critical Error: uvicorn was not installed!${NC}"
    echo -e "${YELLOW}Please check your internet connection and try again.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ All Python packages installed successfully.${NC}"

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
sleep 3
SERVICE_STATUS=$(systemctl is-active "$SERVICE_NAME")

# Fetch Public IP
SERVER_IP=$(curl -s --max-time 3 https://api.ipify.org)
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(curl -s --max-time 3 https://ifconfig.me)
fi
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(hostname -I | awk '{print $1}')
fi

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
echo -e "${BLUE}│  🔄 Update Panel    : ${YELLOW}cd ~/conf-to-sub && git pull && sudo systemctl restart conf-to-sub${BLUE}│${NC}"
echo -e "${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"
echo -e "${GREEN}=======================================================${NC}"
echo -e "${RED}⚠️  IMPORTANT: Ensure port 8000 is open in your firewall!    ${NC}"
echo -e "${GREEN}=======================================================${NC}"
