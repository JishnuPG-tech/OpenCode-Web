#!/bin/sh

echo "============================================"
echo "=== OpenCode Space starting up ==="
echo "Time: $(date)"
echo "============================================"

git config --global --add safe.directory '*' 2>/dev/null || true

# /data is the persistent HF dataset bucket mount
echo "[INIT] Setting up /data directories..."
mkdir -p /data/open-webui 2>/dev/null || echo "[WARN] Could not create /data/open-webui"
mkdir -p /data/omniroute 2>/dev/null || echo "[WARN] Could not create /data/omniroute"
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log \
          /data/jellyfin/media/Movies /data/jellyfin/media/TVShows 2>/dev/null || true

# ── OmniRoute: Local ext4 active DB + backup sync to HF /data ─────────────────
if [ -L "/root/.omniroute" ]; then rm -f /root/.omniroute; fi
mkdir -p /root/.omniroute 2>/dev/null || true

# Restore DB snapshot from persistent volume if no active DB exists
if [ -f "/data/omniroute/storage.sqlite" ] && [ ! -f "/root/.omniroute/storage.sqlite" ]; then
    echo "[INIT] Restoring OmniRoute SQLite snapshot from persistent volume..."
    cp -f /data/omniroute/storage.sqlite /root/.omniroute/storage.sqlite 2>/dev/null || true
    if command -v sqlite3 >/dev/null 2>&1; then
        CHK=$(sqlite3 /root/.omniroute/storage.sqlite "PRAGMA quick_check;" 2>/dev/null || echo "error")
        echo "[INIT] SQLite integrity check: ${CHK}"
    fi
fi

# Clean stale lock files
rm -f /root/.omniroute/*.sqlite-wal /root/.omniroute/*.sqlite-shm /root/.omniroute/*.lock 2>/dev/null || true

# SQLite-aware consistent snapshot backup every 5 minutes
(
    while true; do
        sleep 300
        if [ -f "/root/.omniroute/storage.sqlite" ] && command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 /root/.omniroute/storage.sqlite ".backup /data/omniroute/storage.sqlite" 2>/dev/null || true
        fi
    done
) &

# ── Start Redis ────────────────────────────────────────────────────────────────
echo "[INIT] Starting Redis server on port 6379..."
redis-server --daemonize yes --bind 127.0.0.1 --port 6379 2>/dev/null || echo "[WARN] Redis startup warning"

# ── Start OmniRoute (prebuilt production server from /omniroute) ───────────────
echo "[INIT] Starting OmniRoute AI Gateway (Dashboard: 20128, API: 20129, WS: 20132)..."

export PORT=20128
export API_PORT=20129
export LIVE_WS_PORT=20132
export HOSTNAME="127.0.0.1"
# Override DATA_DIR to use local ext4 instead of FUSE /data mount (avoids SQLite I/O errors)
export DATA_DIR="/root/.omniroute"
export REDIS_URL="redis://127.0.0.1:6379"
export OMNIROUTE_BASE_PATH="/omniroute"
export NEXT_PUBLIC_OMNIROUTE_BASE_PATH="/omniroute"
export NEXT_PUBLIC_BASE_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}/omniroute"
export LIVE_WS_ALLOWED_ORIGINS="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export OMNIROUTE_WS_BRIDGE_SECRET="${OMNIROUTE_WS_BRIDGE_SECRET:-opencode_ws_bridge_secret_2026}"
export JWT_SECRET="${JWT_SECRET:-opencode_jwt_secret_2026}"
export API_KEY_SECRET="${API_KEY_SECRET:-opencode_api_key_secret_2026}"

if [ -d "/omniroute" ]; then
    cd /omniroute
    if [ -f "server.js" ]; then
        node server.js &
    else
        npm run start -- --port 20128 &
    fi
    echo "[INIT] OmniRoute AI Gateway started in background."
else
    echo "[WARN] /omniroute directory not found, skipping OmniRoute startup."
fi

# ── Start Telegram Direct Stream Proxy ────────────────────────────────────────
echo "[INIT] Starting Telegram Direct Stream Proxy on port 8080..."
python3 /tg_streamer.py &

# ── Start Jellyfin Media Server ───────────────────────────────────────────────
echo "[INIT] Starting Jellyfin Media Server on port 8096..."

WEBDIR_OPT=""
if [ -d "/usr/share/jellyfin/web" ]; then
    WEBDIR_OPT="--webdir /usr/share/jellyfin/web"
fi

if command -v jellyfin >/dev/null 2>&1; then
    jellyfin --datadir /data/jellyfin/data --configdir /data/jellyfin/config \
             --cachedir /data/jellyfin/cache --logdir /data/jellyfin/log $WEBDIR_OPT &
    echo "[INIT] Jellyfin server started in background."
elif [ -f "/usr/bin/jellyfin" ]; then
    /usr/bin/jellyfin --datadir /data/jellyfin/data --configdir /data/jellyfin/config \
                      --cachedir /data/jellyfin/cache --logdir /data/jellyfin/log $WEBDIR_OPT &
    echo "[INIT] Jellyfin binary started in background."
else
    echo "[WARN] Could not find jellyfin binary"
fi

mkdir -p /root/.cache /data/cache 2>/dev/null || true
chmod -R 777 /root/.cache /data/cache 2>/dev/null || true

# ── Start Open WebUI ──────────────────────────────────────────────────────────
echo "[INIT] Starting Open WebUI on port 8098 pre-configured with OmniRoute API..."
if command -v open-webui >/dev/null 2>&1; then
    export WEBUI_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
    export OPENAI_API_BASE_URL="http://127.0.0.1:20129/v1"
    export OPENAI_API_KEY="omniroute"
    export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-opencode_webui_jwt_secret_2026}"
    export ENABLE_OLLAMA_API="${ENABLE_OLLAMA_API:-false}"
    export ENABLE_OPENAI_API="true"
    export TOOL_SERVERS=""
    export OPENAPI_TOOL_SERVERS=""
    export PORT=8098
    export DATA_DIR="/data/open-webui"
    mkdir -p /root/.cache /data/cache /data/open-webui 2>/dev/null || true
    if [ ! -L "/root/.open-webui" ]; then
        rm -rf /root/.open-webui 2>/dev/null || true
        ln -sf /data/open-webui /root/.open-webui
    fi
    export CORS_ALLOW_ORIGIN="*"
    export RAG_AUTO_UPDATE_INDEX="false"
    export HF_HUB_ENABLE_HF_TRANSFER="1"
    export WEBUI_AUTH="true"
    export ENABLE_SIGNUP="true"
    open-webui serve --port 8098 &
    echo "[INIT] Open WebUI started in background."
else
    echo "[WARN] open-webui binary not found, skipping."
fi

echo "[DISK] /data usage:"
df -h /data 2>/dev/null || echo "[WARN] Could not check /data disk space"

echo "============================================"
echo "=== Launching FastAPI Gateway Proxy on Port 4096 ==="
echo "============================================"

cd /
exec python3 -m uvicorn proxy:app --host 0.0.0.0 --port 4096
