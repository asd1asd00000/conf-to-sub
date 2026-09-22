#!/usr/bin/env bash
set -e

# ===== Fixed settings =====
GITHUB_USER="asd1asd00000"
REPO="conf-to-sub"
APP_DIR="/root/$REPO"
SERVICE_NAME="conf-to-sub"
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

echo "=================================================="
echo " Gift Panel Installer"
echo "=================================================="

# ===== 1) Domain =====
read -p "🌐 Enter panel domain (e.g., panel.example.com): " DOMAIN
if [ -z "$DOMAIN" ]; then
    echo "❌ Domain cannot be empty!"; exit 1
fi

# ===== 2) Admin credentials =====
read -p "👤 Admin username [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}
read -s -p "🔑 Admin password (empty = auto-generate): " ADMIN_PASS
echo ""
GENERATED_PASS=""
if [ -z "$ADMIN_PASS" ]; then
    ADMIN_PASS=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-14)
    GENERATED_PASS=" (auto-generated)"
fi

echo ""
echo "📦 Starting installation..."

# ===== 3) Prerequisites =====
apt update -y
apt install -y git python3-venv python3-pip nginx certbot python3-certbot-nginx sqlite3 curl

# ===== 4) Download project =====
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR" && git pull origin main || true
else
    cd /root
    git clone "https://github.com/$GITHUB_USER/$REPO.git" || {
        echo "❌ Repository not found: $GITHUB_USER/$REPO"; exit 1;
    }
    cd "$APP_DIR"
fi

# ===== 5) Virtual environment =====
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q -i "$PIP_MIRROR" --trusted-host pypi.tuna.tsinghua.edu.cn

# ===== 6) Build local CSS (Tailwind) =====
echo "🎨 Building local CSS..."
chmod +x build_css.sh 2>/dev/null || true
./build_css.sh || {
    echo "❌ CSS build failed! Panel needs app/static/style.css to render."
    echo "   Try manually: ./build_css.sh"
    exit 1
}

# ===== 7) Systemd service =====
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=Gift Panel (conf-to-sub) FastAPI Service
After=network.target

[Service]
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME
sleep 3

# ===== 8) Nginx Reverse Proxy =====
cat > /etc/nginx/sites-available/$SERVICE_NAME <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# ===== 9) SSL (Let's Encrypt) =====
echo "🔐 Obtaining SSL certificate for $DOMAIN ..."
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" --redirect \
    && echo "✅ SSL enabled!" \
    || echo "⚠️  SSL failed! Make sure DNS points to this server. (HTTP for now)"

# ===== 10) Set admin credentials =====
cd "$APP_DIR"
./venv/bin/python set_admin.py "$ADMIN_USER" "$ADMIN_PASS"

# ===== 11) Final summary with table =====
PANEL_URL="https://$DOMAIN/admin/"
W1=20  # label width
W2=42  # value width
TOTAL=$((W1 + W2 + 7))
LINE=$(printf '═%.0s' $(seq 1 $TOTAL))

echo ""
printf "\033[1;32m╔%s╗\033[0m\n" "$LINE"
printf "\033[1;32m║\033[1;32m  ✅ Installation Complete!%*s\033[0m\033[1;32m║\033[0m\n" $((TOTAL - 31)) ""
printf "\033[1;32m╠%s╣\033[0m\n" "$LINE"
printf "\033[1;32m║\033[0m %-*s\033[1;32m│\033[0m \033[1;36m%s\033[0m%*s\033[1;32m║\033[0m\n" $W1 "🌐 Panel URL" "${PANEL_URL}" $((W2 - ${#PANEL_URL})) ""
printf "\033[1;32m║\033[0m %-*s\033[1;32m│\033[0m \033[1;33m%s\033[0m%*s\033[1;32m║\033[0m\n" $W1 "👤 Username" "${ADMIN_USER}" $((W2 - ${#ADMIN_USER})) ""
printf "\033[1;32m║\033[0m %-*s\033[1;32m│\033[0m \033[1;33m%s\033[0m%*s\033[1;32m║\033[0m\n" $W1 "🔑 Password" "${ADMIN_PASS}" $((W2 - ${#ADMIN_PASS})) ""
printf "\033[1;32m║\033[0m %-*s\033[1;32m│\033[0m \033[0;37m%s\033[0m%*s\033[1;32m║\033[0m\n" $W1 "📝 Note" "${GENERATED_PASS:-(user-defined)}" $((W2 - ${#GENERATED_PASS} + 16)) ""
printf "\033[1;32m╠%s╣\033[0m\n" "$LINE"
printf "\033[1;32m║\033[0m  \033[1;31m⚠️  Save these credentials now!\033[0m%*s\033[1;32m║\033[0m\n" $((TOTAL - 36)) ""
printf "\033[1;32m║\033[0m  \033[0;37m🔧 Change later: \033[1;37m./venv/bin/python set_admin.py USER PASS\033[0m%*s\033[1;32m║\033[0m\n" $((TOTAL - 60)) ""
printf "\033
