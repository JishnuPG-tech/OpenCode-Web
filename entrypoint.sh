#!/bin/sh

echo "============================================"
echo "=== OpenCode Space starting up ==="
echo "Time: $(date)"
echo "============================================"

git config --global --add safe.directory '*' 2>/dev/null || true

# ── Load secrets from data bucket (before :? validation runs) ─────────────────
# Load ALL matching env files so partial secret files can be combined.
# Checks both /data/ root and /data/omniroute/ (where persistent config is stored).
for _ENV_FILE in \
    "/data/.env" \
    "/data/secrets.env" \
    "/data/secrets" \
    "/data/config/.env" \
    "/data/omniroute/.env" \
    "/data/omniroute/secrets.env" \
    "/data/omniroute/secrets" \
    "/data/omniroute/.secrets" \
    "/data/omniroute/server.env"; do
    if [ -f "$_ENV_FILE" ]; then
        echo "[INIT] Loading secrets from ${_ENV_FILE}..."
        set -a
        # shellcheck disable=SC1090
        . "$_ENV_FILE"
        set +a
        echo "[INIT] Secrets loaded from ${_ENV_FILE}"
    fi
done
unset _ENV_FILE

# Debug: show which required secrets are still missing (without printing values)
for _VAR in JWT_SECRET API_KEY_SECRET OMNIROUTE_WS_BRIDGE_SECRET WEBUI_SECRET_KEY; do
    eval _VAL=\$$_VAR
    if [ -z "$_VAL" ]; then
        echo "[WARN] ${_VAR} is not set after loading env files"
    else
        echo "[INIT] ${_VAR} is set (${#_VAL} chars)"
    fi
done
unset _VAR _VAL

# /data is the persistent HF dataset bucket mount
echo "[INIT] Setting up /data directories..."
mkdir -p /data/open-webui 2>/dev/null || echo "[WARN] Could not create /data/open-webui"
mkdir -p /data/omniroute 2>/dev/null || echo "[WARN] Could not create /data/omniroute"
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log \
          /data/jellyfin/media/Movies /data/jellyfin/media/TVShows 2>/dev/null || true

# ── OmniRoute: Local ext4 active DB + backup sync to HF /data ─────────────────
if [ -L "/root/.omniroute" ]; then rm -f /root/.omniroute; fi
mkdir -p /root/.omniroute 2>/dev/null || true

# Restore DB snapshot from persistent volume if a non-empty DB exists in /data
_RESTORED=0
for _DB_CANDIDATE in \
    "/data/omniroute/storage.sqlite" \
    "/data/omniroute.sqlite" \
    "/data/storage.sqlite" \
    "/data/omniroute/db.sqlite" \
    "/data/omniroute/omniroute.db" \
    "/data/db.sqlite"; do
    if [ -f "$_DB_CANDIDATE" ] && [ -s "$_DB_CANDIDATE" ]; then
        echo "[INIT] Restoring OmniRoute database from ${_DB_CANDIDATE}..."
        cp -f "$_DB_CANDIDATE" /root/.omniroute/storage.sqlite 2>/dev/null || true
        _RESTORED=1
        if command -v sqlite3 >/dev/null 2>&1; then
            CHK=$(sqlite3 /root/.omniroute/storage.sqlite "PRAGMA quick_check;" 2>/dev/null || echo "error")
            echo "[INIT] SQLite integrity check for ${_DB_CANDIDATE}: ${CHK}"
        fi
        break
    fi
done
if [ "$_RESTORED" -eq 0 ]; then
    echo "[INIT] No pre-existing database snapshot found in /data. Starting with fresh DB."
fi
unset _DB_CANDIDATE _RESTORED

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

# Default admin credentials for OmniRoute
export INITIAL_PASSWORD="${INITIAL_PASSWORD:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
export OMNIROUTE_INITIAL_PASSWORD="${OMNIROUTE_INITIAL_PASSWORD:-admin}"

# Required secrets — crash early with a clear message if missing
export JWT_SECRET="${JWT_SECRET:?JWT_SECRET is not set. Add it to /data/.env or Space Secrets.}"
export API_KEY_SECRET="${API_KEY_SECRET:?API_KEY_SECRET is not set. Add it to /data/.env or Space Secrets.}"

# Optional secrets — auto-generate from JWT_SECRET if not explicitly set
# OMNIROUTE_WS_BRIDGE_SECRET: used only for the Live WebSocket monitoring bridge (port 20132)
if [ -z "$OMNIROUTE_WS_BRIDGE_SECRET" ]; then
    OMNIROUTE_WS_BRIDGE_SECRET="ws_bridge_$(echo "$JWT_SECRET" | sha256sum | cut -c1-48 2>/dev/null || echo "$JWT_SECRET" | md5sum | cut -c1-32)"
    echo "[INIT] OMNIROUTE_WS_BRIDGE_SECRET auto-generated (add to /data/.env to make permanent)"
fi
export OMNIROUTE_WS_BRIDGE_SECRET

# WEBUI_SECRET_KEY: Open WebUI JWT signing secret (must be ≥32 chars)
if [ -z "$WEBUI_SECRET_KEY" ]; then
    WEBUI_SECRET_KEY="owui_$(echo "${JWT_SECRET}openwebui" | sha256sum | cut -c1-56 2>/dev/null || echo "${JWT_SECRET}openwebui" | md5sum | cut -c1-32)"
    echo "[INIT] WEBUI_SECRET_KEY auto-generated (add to /data/.env to make permanent)"
fi
export WEBUI_SECRET_KEY

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
    export WEBUI_SECRET_KEY="$WEBUI_SECRET_KEY"
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
