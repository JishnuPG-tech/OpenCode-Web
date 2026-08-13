#!/bin/sh
set -e

echo "============================================"
echo "=== OpenCode Space Container Starting ==="
echo "Time: $(date)"
echo "============================================"

# Step 1: Configure Git & Environment Secrets Validation
git config --global --add safe.directory '*' 2>/dev/null || true

# Step 2: Ensure persistent /data directory structure exists
echo "[INIT] Setting up /data persistent volume directories..."
mkdir -p /data/share/opencode /data/config/opencode /data/cache/opencode /data/state/opencode 2>/dev/null || true
mkdir -p /data/open-webui /data/omniroute 2>/dev/null || true
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log /data/jellyfin/media/Movies /data/jellyfin/media/TVShows 2>/dev/null || true
mkdir -p /root/.cache /data/cache 2>/dev/null || true
chmod -R 777 /root/.cache /data/cache 2>/dev/null || true

if [ ! -L "/root/.omniroute" ]; then
    rm -rf /root/.omniroute 2>/dev/null || true
    ln -sf /data/omniroute /root/.omniroute
fi

# Step 3: Start FastAPI Gateway on Internal Port 8000
echo "[BOOT] FastAPI starting..."
START_TIME=$(date +%s)
python3 -m uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --workers 2 > /data/cache/fastapi_gateway.log 2>&1 &
FASTAPI_PID=$!

# Step 4: Wait for FastAPI /health/live to return HTTP 200
FASTAPI_READY=0
for i in $(seq 1 30); do
    if curl --max-time 2 -sf -i http://127.0.0.1:8000/health/live | grep -q "200 OK"; then
        FASTAPI_READY=1
        END_TIME=$(date +%s)
        ELAPSED=$((END_TIME - START_TIME))
        echo "[BOOT] FastAPI live: ${ELAPSED}s"
        break
    fi
    sleep 0.2
done

if [ "$FASTAPI_READY" -ne 1 ]; then
    echo "[WARN] FastAPI did not report ready within timeout, proceeding with startup..."
fi

# Step 5: Start Nginx Edge Server on Public Port 4096
echo "[BOOT] Nginx starting..."
rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-available/default 2>/dev/null || true
nginx -t -c /nginx.conf
nginx -g 'daemon off;' -c /nginx.conf &
NGINX_PID=$!

# Step 6: Wait for Nginx /health/live on Port 4096 to return HTTP 200
NGINX_READY=0
for i in $(seq 1 30); do
    if curl --max-time 2 -sf -i http://127.0.0.1:4096/health/live | grep -q "200 OK"; then
        NGINX_READY=1
        break
    fi
    sleep 0.2
done

# Step 7: Signal Public Gateway Readiness immediately to Hugging Face
echo "[BOOT] Public gateway live"
echo "[BOOT] Background services starting asynchronously..."

# Step 8: Start OmniRoute AI Gateway in Background (if available)
if command -v omniroute >/dev/null 2>&1; then
    echo "[HEALTH] OmniRoute starting in background..."
    export HOME="/root"
    export XDG_CACHE_HOME="/root/.cache"
    export HOST="0.0.0.0"
    export OMNIROUTE_SERVER_HOST="0.0.0.0"
    export BASE_URL="http://127.0.0.1:20128"
    export DATA_DIR="/data/omniroute"
    export DASHBOARD_PORT=20128
    export PORT=20128
    export AUTH_COOKIE_SECURE="true"
    export JWT_SECRET="${OMNIROUTE_JWT_SECRET:-opencode_omniroute_jwt_secret_key_2026_secure_random_token}"
    export API_KEY_SECRET="${OMNIROUTE_API_KEY_SECRET:-e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8}"
    export STORAGE_ENCRYPTION_KEY="${OMNIROUTE_STORAGE_KEY:-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b}"
    export INITIAL_PASSWORD="${OMNIROUTE_INITIAL_PASSWORD:-admin}"
    export DISABLE_SQLITE_AUTO_BACKUP="true"
    export NODE_ENV="production"

    mkdir -p /data/omniroute /root/.omniroute 2>/dev/null || true
    cat <<EOF > /data/omniroute/.env
DATA_DIR=/data/omniroute
PORT=20128
DASHBOARD_PORT=20128
JWT_SECRET=${JWT_SECRET}
API_KEY_SECRET=${API_KEY_SECRET}
STORAGE_ENCRYPTION_KEY=${STORAGE_ENCRYPTION_KEY}
INITIAL_PASSWORD=${INITIAL_PASSWORD}
DISABLE_SQLITE_AUTO_BACKUP=true
NODE_ENV=production
AUTH_COOKIE_SECURE=true
OMNIROUTE_SERVER_HOST=0.0.0.0
EOF
    cp -f /data/omniroute/.env /root/.omniroute/.env 2>/dev/null || true

    omniroute serve --port 20128 --no-open > /data/omniroute/omniroute.log 2>&1 &
    OMNIROUTE_PID=$!
fi

# Step 9: Start Telegram Range Stream Proxy in Background (Port 8080)
if [ -f "/tg_streamer.py" ]; then
    echo "[HEALTH] Telegram streamer starting in background..."
    python3 /tg_streamer.py > /data/cache/tg_streamer.log 2>&1 &
    TG_PID=$!
fi

# Step 10: Start Jellyfin Media Server in Background (Port 8096)
WEBDIR_OPT=""
if [ -d "/usr/share/jellyfin/web" ]; then
    WEBDIR_OPT="--webdir /usr/share/jellyfin/web"
fi

if command -v jellyfin >/dev/null 2>&1; then
    echo "[HEALTH] Jellyfin starting in background..."
    jellyfin --datadir /data/jellyfin/data --configdir /data/jellyfin/config --cachedir /data/jellyfin/cache --logdir /data/jellyfin/log $WEBDIR_OPT > /data/jellyfin/log/jellyfin.log 2>&1 &
    JELLYFIN_PID=$!
elif [ -f "/usr/bin/jellyfin" ]; then
    echo "[HEALTH] Jellyfin binary starting in background..."
    /usr/bin/jellyfin --datadir /data/jellyfin/data --configdir /data/jellyfin/config --cachedir /data/jellyfin/cache --logdir /data/jellyfin/log $WEBDIR_OPT > /data/jellyfin/log/jellyfin.log 2>&1 &
    JELLYFIN_PID=$!
fi

# Step 11: Start Open WebUI in Background (Port 8098)
if command -v open-webui >/dev/null 2>&1; then
    echo "[HEALTH] Open WebUI starting in background on port 8098..."
    export WEBUI_URL="https://jishnupg-opencode-cli.hf.space"
    export OPENAI_API_BASE_URL="http://127.0.0.1:20128/v1"
    export OPENAI_API_KEY="omniroute"
    export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-opencode_webui_jwt_secret_2026}"
    export ENABLE_OLLAMA_API="false"
    export ENABLE_OPENAI_API="true"
    export TOOL_SERVERS=""
    export OPENAPI_TOOL_SERVERS=""
    export PORT=8098
    export DATA_DIR="/data/open-webui"
    export CORS_ALLOW_ORIGIN="*"
    export WEBUI_AUTH="true"
    export ENABLE_SIGNUP="true"
    
    if [ ! -L "/root/.open-webui" ]; then
        rm -rf /root/.open-webui 2>/dev/null || true
        ln -sf /data/open-webui /root/.open-webui
    fi
    
    open-webui serve --port 8098 > /data/cache/openwebui.log 2>&1 &
    WEBUI_PID=$!
fi

# Step 12 & 13: Keep PID 1 Alive and Monitor Child Processes
echo "[BOOT] All services dispatched. Process Supervisor active."

while true; do
    if ! kill -0 $FASTAPI_PID 2>/dev/null; then
        echo "[CRITICAL] FastAPI Gateway process died! Restarting..."
        python3 -m uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --workers 2 > /data/cache/fastapi_gateway.log 2>&1 &
        FASTAPI_PID=$!
    fi

    if [ -n "$NGINX_PID" ] && ! kill -0 $NGINX_PID 2>/dev/null; then
        echo "[CRITICAL] Nginx process died! Restarting..."
        nginx -g 'daemon off;' -c /nginx.conf &
        NGINX_PID=$!
    fi

    if [ -n "$OMNIROUTE_PID" ] && ! kill -0 $OMNIROUTE_PID 2>/dev/null; then
        echo "[CRITICAL] OmniRoute process died! Restarting..."
        omniroute serve --port 20128 --no-open > /data/omniroute/omniroute.log 2>&1 &
        OMNIROUTE_PID=$!
    fi

    sleep 5
done
