#!/bin/bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Updating Gift Panel...${NC}"

# Pull latest changes from GitHub
git pull

# Update Python dependencies if venv exists
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install -r requirements.txt
fi

# Restart the service
sudo systemctl restart conf-to-sub

echo -e "${GREEN}Update Complete! Panel restarted successfully.${NC}"
