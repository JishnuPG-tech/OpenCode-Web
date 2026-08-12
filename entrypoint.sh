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
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log /data/jellyfin/media/Movies /data/jellyfin/media/TVShows 2>/dev/null || true

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
sleep 3


# Ensure cache directories exist
mkdir -p /root/.cache /data/cache 2>/dev/null || true
chmod -R 777 /root/.cache /data/cache 2>/dev/null || true
sleep 2

# Pre-configure & Start Open WebUI on port 8098 (Mounted at / via FastAPI proxy)
echo "[INIT] Starting Open WebUI on port 8098..."
if command -v open-webui >/dev/null 2>&1; then
    # Tell Open WebUI its public-facing URL
    export WEBUI_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
    export OPENAI_API_BASE_URL="${OPENAI_API_BASE_URL:-https://api.openai.com/v1}"
    export OPENAI_API_KEY="${OPENAI_API_KEY:-}"
    export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-opencode_webui_jwt_secret_2026}"
    export ENABLE_OLLAMA_API="${ENABLE_OLLAMA_API:-false}"
    export ENABLE_OPENAI_API="${ENABLE_OPENAI_API:-true}"
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
    # Allow requests from all origins (including public HF Space origin & websockets)
    export CORS_ALLOW_ORIGIN="*"
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
