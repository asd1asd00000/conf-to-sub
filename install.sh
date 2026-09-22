#!/usr/bin/env bash
set -e

# ===== تنظیمات ثابت =====
GITHUB_USER="asd1asd00000"
REPO="conf-to-sub"
APP_DIR="/root/$REPO"
SERVICE_NAME="conf-to-sub"
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

echo "=================================================="
echo " Gift Panel Installer"
echo "=================================================="

# ===== ۱) دامنه =====
read -p "🌐 دامنه پنل را وارد کنید (مثال: panel.example.com): " DOMAIN
if [ -z "$DOMAIN" ]; then
    echo "❌ دامنه خالی است!"; exit 1
fi

# ===== ۲) اعتبارنامه ادمین =====
read -p "👤 نام کاربری ادمین [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}
read -s -p "🔑 رمز عبور ادمین (خالی = تولید خودکار): " ADMIN_PASS
echo ""
GENERATED_PASS=""
if [ -z "$ADMIN_PASS" ]; then
    ADMIN_PASS=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-14)
    GENERATED_PASS="(تولید خودکار)"
fi

echo ""
echo "📦 شروع نصب..."

# ===== ۳) پیش‌نیازها =====
apt update -y
apt install -y git python3-venv python3-pip nginx certbot python3-certbot-nginx sqlite3 curl

# ===== ۴) دانلود پروژه =====
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR" && git pull origin main || true
else
    cd /root
    git clone "https://github.com/$GITHUB_USER/$REPO.git" || {
        echo "❌ Repository not found: $GITHUB_USER/$REPO"; exit 1;
    }
    cd "$APP_DIR"
fi

# ===== ۵) محیط مجازی =====
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q -i "$PIP_MIRROR" --trusted-host pypi.tuna.tsinghua.edu.cn

# ===== ۶) ساخت CSS محلی (Tailwind build) =====
echo "🎨 Building local CSS..."
chmod +x build_css.sh 2>/dev/null || true
./build_css.sh || {
    echo "❌ CSS build failed! Panel needs app/static/style.css to render."
    echo "   Try manually: ./build_css.sh"
    exit 1
}

# ===== ۷) سرویس systemd =====
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

# ===== ۸) Nginx Reverse Proxy =====
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

# ===== ۹) SSL (Let's Encrypt) =====
echo "🔐 دریافت گواهی SSL برای $DOMAIN ..."
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" --redirect \
    && echo "✅ SSL فعال شد!" \
    || echo "⚠️  SSL ناموفق! مطمئن شوید DNS دامنه به همین سرور اشاره می‌کند. (فعلاً HTTP)"

# ===== ۱۰) ساخت اعتبارنامه ادمین =====
cd "$APP_DIR"
./venv/bin/python set_admin.py "$ADMIN_USER" "$ADMIN_PASS"

# ===== ۱۱) خلاصه نهایی =====
echo ""
echo "=================================================="
echo "✅ نصب کامل شد!"
echo "=================================================="
echo "🌐 آدرس پنل:      https://$DOMAIN/admin/"
echo "👤 نام کاربری:    $ADMIN_USER"
echo "🔑 رمز عبور:      $ADMIN_PASS  $GENERATED_PASS"
echo "--------------------------------------------------"
echo "⚠️  این اطلاعات را همین الان ذخیره کنید!"
echo "🔧 تغییر بعدی:    ./venv/bin/python set_admin.py USER PASS"
echo "🎨 بعد از تغییر قالب: ./build_css.sh"
echo "=================================================="
