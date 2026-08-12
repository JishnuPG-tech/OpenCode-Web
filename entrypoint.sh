#!/bin/sh

echo "============================================"
echo "=== OpenCode Space starting up ==="
echo "Time: $(date)"
echo "============================================"

# Configure Git to trust all directories to prevent ownership errors
git config --global --add safe.directory '*' 2>/dev/null || true

# /data is the persistent HF dataset bucket mount
echo "[INIT] Setting up /data directories..."
mkdir -p /data/open-webui 2>/dev/null || echo "[WARN] Could not create /data/open-webui"
mkdir -p /data/omniroute 2>/dev/null || echo "[WARN] Could not create /data/omniroute"
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log /data/jellyfin/media/Movies /data/jellyfin/media/TVShows 2>/dev/null || true

# OmniRoute data directory setup (Local ext4 for SQLite locks + background sync to HF persistent /data mount)
if [ -L "/root/.omniroute" ]; then
    rm -f /root/.omniroute
fi
mkdir -p /root/.omniroute /data/omniroute 2>/dev/null || true

# Restore existing DB from persistent volume if available with quick_check validation
if [ -f "/data/omniroute/storage.sqlite" ] && [ ! -f "/root/.omniroute/storage.sqlite" ]; then
    echo "[INIT] Restoring OmniRoute SQLite database snapshot from persistent volume..."
    cp -f /data/omniroute/storage.sqlite /root/.omniroute/storage.sqlite 2>/dev/null || true
    if command -v sqlite3 >/dev/null 2>&1; then
        CHK=$(sqlite3 /root/.omniroute/storage.sqlite "PRAGMA quick_check;" 2>/dev/null || echo "error")
        echo "[INIT] SQLite restored snapshot integrity check: ${CHK}"
    fi
fi

# Clean up stale lock files
rm -f /root/.omniroute/*.sqlite-wal /root/.omniroute/*.sqlite-shm /root/.omniroute/*.lock 2>/dev/null || true

# Start Redis server for OmniRoute distributed caching and rate limiting
echo "[INIT] Starting Redis server on port 6379..."
redis-server --daemonize yes --bind 127.0.0.1 --port 6379 2>/dev/null || echo "[WARN] Redis server startup warning"

# Safe SQLite Backup Process (Uses sqlite3 .backup API every 5 mins for consistent snapshot)
(
    while true; do
        sleep 300
        if [ -f "/root/.omniroute/storage.sqlite" ] && command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 /root/.omniroute/storage.sqlite ".backup /data/omniroute/storage.sqlite" 2>/dev/null || true
        fi
    done
) &

# Start OmniRoute AI Gateway (Multi-Port: Dashboard: 20128, Dedicated API: 20129, Live WS: 20132)
echo "[INIT] Starting OmniRoute AI Gateway (Dashboard: 20128, API: 20129, WS: 20132)..."
export PORT=20128
export API_PORT=20129
export LIVE_WS_PORT=20132
export HOSTNAME="127.0.0.1"
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
    # Run migration version repair for runtime database safety
    python3 /fix_omniroute.py /omniroute 2>/dev/null || true
    python3 /fix_omniroute.py /root/.omniroute 2>/dev/null || true

    if [ -f "server.js" ]; then
        node server.js &
    else
        echo "[INIT] Starting pre-compiled OmniRoute production server..."
        npm run start -- --port 20128 &
    fi
    echo "[INIT] OmniRoute AI Gateway started in background."
else
    echo "[WARN] /omniroute directory not found, skipping OmniRoute startup."
fi

# Start Telegram Direct Range Stream Proxy in background
echo "[INIT] Starting Telegram Direct Stream Proxy on port 8080..."
python3 /tg_streamer.py &

# Start Jellyfin Media Server in background
echo "[INIT] Starting Jellyfin Media Server on port 8096..."

WEBDIR_OPT=""
if [ -d "/usr/share/jellyfin/web" ]; then
    WEBDIR_OPT="--webdir /usr/share/jellyfin/web"
fi

if command -v jellyfin >/dev/null 2>&1; then
    jellyfin --datadir /data/jellyfin/data --configdir /data/jellyfin/config --cachedir /data/jellyfin/cache --logdir /data/jellyfin/log $WEBDIR_OPT &
    echo "[INIT] Jellyfin server started in background."
elif [ -f "/usr/bin/jellyfin" ]; then
    /usr/bin/jellyfin --datadir /data/jellyfin/data --configdir /data/jellyfin/config --cachedir /data/jellyfin/cache --logdir /data/jellyfin/log $WEBDIR_OPT &
    echo "[INIT] Jellyfin binary started in background."
else
    echo "[WARN] Could not find jellyfin binary"
fi

# Ensure cache directories exist
mkdir -p /root/.cache /data/cache 2>/dev/null || true
chmod -R 777 /root/.cache /data/cache 2>/dev/null || true

# Pre-configure & Start Open WebUI on port 8098 (Mounted at / via FastAPI proxy)
echo "[INIT] Starting Open WebUI on port 8098 pre-configured with OmniRoute API..."
if command -v open-webui >/dev/null 2>&1; then
    # Point OpenAI API to OmniRoute dedicated API port 20129
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
    # Sanitize any stale tool server entries in webui.db
    python3 -c "
import sqlite3, os
db_p = '/data/open-webui/webui.db'
if os.path.exists(db_p):
    try:
        conn = sqlite3.connect(db_p)
        cur = conn.cursor()
        cur.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='config'\")
        if cur.fetchone():
            cur.execute(\"DELETE FROM config WHERE key LIKE '%tool%' AND (value LIKE '%jishnupg%' OR value LIKE '%openapi%')\")
            conn.commit()
        conn.close()
        print('[CONFIG] Sanitized Open WebUI database tool server entries.')
    except Exception as e:
        print('[CONFIG] WebUI DB sanitize note:', e)
" 2>/dev/null || true
    export CORS_ALLOW_ORIGIN="*"
    export RAG_AUTO_UPDATE_INDEX="false"
    export HF_HUB_ENABLE_HF_TRANSFER="1"
    # Enable authentication so user can log in / log out cleanly with saved credentials
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
