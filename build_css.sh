#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -x ./tailwindcss ]; then
    echo "❌ tailwindcss binary not found. Run: curl -L -o tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64 && chmod +x tailwindcss"
    exit 1
fi
./tailwindcss -i app/static/input.css -o app/static/style.css --minify
SIZE=$(du -h app/static/style.css | cut -f1)
echo "✅ Built app/static/style.css ($SIZE)"
