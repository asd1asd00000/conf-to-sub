#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -x ./tailwindcss ]; then
    echo "📥 Downloading Tailwind CSS CLI..."
    curl -fL -o tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64 \
        || { echo "❌ Failed to download Tailwind CLI. Check internet/GitHub access."; exit 1; }
    chmod +x tailwindcss
fi

./tailwindcss -i app/static/input.css -o app/static/style.css --minify
SIZE=$(du -h app/static/style.css | cut -f1)
echo "✅ Built app/static/style.css ($SIZE)"
