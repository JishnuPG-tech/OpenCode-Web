#!/bin/sh

echo "============================================"
echo "=== OpenCode Space starting up ==="
echo "Time: $(date)"
echo "============================================"

git config --global --add safe.directory '*' 2>/dev/null || true

# ── Load secrets from data bucket (before :? validation runs) ─────────────────
# Check candidate locations in order of preference.
# Format: KEY=value lines, one per line. Lines starting with # are ignored.
for _ENV_FILE in "/data/.env" "/data/secrets.env" "/data/secrets" "/data/config/.env"; do
    if [ -f "$_ENV_FILE" ]; then
        echo "[INIT] Loading secrets from ${_ENV_FILE}..."
        set -a
        # shellcheck disable=SC1090
        . "$_ENV_FILE"
        set +a
        echo "[INIT] Secrets loaded from ${_ENV_FILE}"
        break
    fi
done
unset _ENV_FILE

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
# Override DATA_DIR to local ext4 to avoid SQLite FUSE I/O errors on HF /data
export DATA_DIR="/root/.omniroute"
export REDIS_URL="redis://127.0.0.1:6379"
export OMNIROUTE_BASE_PATH="/omniroute"
export NEXT_PUBLIC_OMNIROUTE_BASE_PATH="/omniroute"
export NEXT_PUBLIC_BASE_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}/omniroute"
export LIVE_WS_ALLOWED_ORIGINS="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export OMNIROUTE_WS_BRIDGE_SECRET="${OMNIROUTE_WS_BRIDGE_SECRET:?OMNIROUTE_WS_BRIDGE_SECRET is not set in Space Secrets}"
export JWT_SECRET="${JWT_SECRET:?JWT_SECRET is not set in Space Secrets}"
export API_KEY_SECRET="${API_KEY_SECRET:?API_KEY_SECRET is not set in Space Secrets}"

if [ -d "/omniroute" ]; then
    cd /omniroute
    if [ -f "server.js" ]; then
        node server.js &
    else
        npm run start -- --port 20128 &
    fi
    OMNIROUTE_PID=$!
    echo "[INIT] OmniRoute AI Gateway PID=${OMNIROUTE_PID} — waiting for health..."

    OMNIROUTE_HEALTHY=0
    for i in $(seq 1 90); do
        if ! kill -0 "$OMNIROUTE_PID" 2>/dev/null; then
            echo "[ERROR] OmniRoute exited during startup (PID=${OMNIROUTE_PID}). Aborting."
            wait "$OMNIROUTE_PID"
            exit 1
        fi
        if curl -fsS "http://127.0.0.1:20128/api/monitoring/health" >/dev/null 2>&1; then
            echo "[HEALTH] OmniRoute dashboard healthy after ${i}s"
            OMNIROUTE_HEALTHY=1
            break
        fi
        sleep 1
    done

    if [ "$OMNIROUTE_HEALTHY" -eq 0 ]; then
        echo "[ERROR] OmniRoute did not become healthy within 90 seconds."
        kill "$OMNIROUTE_PID" 2>/dev/null || true
        exit 1
    fi
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
    export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:?WEBUI_SECRET_KEY is not set in Space Secrets}"
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
    # Persist Hugging Face model cache to /data so it survives restarts
    export HF_HOME="/data/cache/huggingface"
    export SENTENCE_TRANSFORMERS_HOME="/data/cache/sentence_transformers"
    mkdir -p "$HF_HOME" "$SENTENCE_TRANSFORMERS_HOME" 2>/dev/null || true
    export CORS_ALLOW_ORIGIN="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
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
