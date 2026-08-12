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

# Ensure deterministic, permanent secrets if not explicitly set
export JWT_SECRET="${JWT_SECRET:-$(echo "opencode_jwt_secret_hf_space_key_2026" | sha256sum | cut -c1-48)}"
export API_KEY_SECRET="${API_KEY_SECRET:-$(echo "opencode_api_key_secret_hf_space_key_2026" | sha256sum | cut -c1-64)}"
export OMNIROUTE_WS_BRIDGE_SECRET="${OMNIROUTE_WS_BRIDGE_SECRET:-$(echo "ws_bridge_${JWT_SECRET}" | sha256sum | cut -c1-48)}"
export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-$(echo "owui_${JWT_SECRET}" | sha256sum | cut -c1-56)}"

# Debug: show secret statuses
for _VAR in JWT_SECRET API_KEY_SECRET OMNIROUTE_WS_BRIDGE_SECRET WEBUI_SECRET_KEY; do
    eval _VAL=\$$_VAR
    echo "[INIT] ${_VAR} is configured (${#_VAL} chars)"
done
unset _VAR _VAL

# /data is the persistent HF dataset bucket mount
echo "[INIT] Setting up /data directories..."
mkdir -p /data/open-webui 2>/dev/null || echo "[WARN] Could not create /data/open-webui"
mkdir -p /data/omniroute 2>/dev/null || echo "[WARN] Could not create /data/omniroute"
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log \
          /data/jellyfin/media/Movies /data/jellyfin/media/TVShows 2>/dev/null || true

# ── OmniRoute Database Restoration & Persistent Synchronization ────────────────
mkdir -p /root/.omniroute /data/omniroute 2>/dev/null || true

_RESTORED=0
if [ -d "/data/omniroute" ] && [ -f "/data/omniroute/storage.sqlite" ] && [ -s "/data/omniroute/storage.sqlite" ]; then
    echo "[INIT] Restoring persistent OmniRoute database snapshot from /data/omniroute..."
    cp -af /data/omniroute/storage.sqlite* /root/.omniroute/ 2>/dev/null || cp -f /data/omniroute/storage.sqlite /root/.omniroute/storage.sqlite 2>/dev/null || true
    _RESTORED=1
else
    for _DB_CANDIDATE in "/data/omniroute.sqlite" "/data/storage.sqlite" "/data/db.sqlite"; do
        if [ -f "$_DB_CANDIDATE" ] && [ -s "$_DB_CANDIDATE" ]; then
            echo "[INIT] Restoring OmniRoute database from ${_DB_CANDIDATE}..."
            cp -f "$_DB_CANDIDATE" /root/.omniroute/storage.sqlite 2>/dev/null || true
            _RESTORED=1
            break
        fi
    done
fi

if [ "$_RESTORED" -eq 0 ]; then
    echo "[INIT] No pre-existing database snapshot found in /data. Starting with fresh DB."
fi
unset _DB_CANDIDATE _RESTORED

# Continuous synchronization function (copies sqlite DB + WAL + SHM files)
sync_omniroute_db() {
    if [ -f "/root/.omniroute/storage.sqlite" ]; then
        mkdir -p /data/omniroute 2>/dev/null || true
        cp -af /root/.omniroute/storage.sqlite* /data/omniroute/ 2>/dev/null || true
    fi
}

# Sync immediately at startup
sync_omniroute_db

# Flush to persistent storage on container shutdown
trap sync_omniroute_db EXIT INT TERM

# High-frequency background sync every 15 seconds
(
    while true; do
        sleep 15
        sync_omniroute_db
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

# Public Base URL and Origin settings for OAuth and WebSockets
export APP_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export PUBLIC_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export BASE_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export NEXT_PUBLIC_BASE_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export NEXT_PUBLIC_APP_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export OMNIROUTE_PUBLIC_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export OMNIROUTE_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export OMNIROUTE_BASE_PATH=""
export NEXT_PUBLIC_OMNIROUTE_BASE_PATH=""
export LIVE_WS_ALLOWED_ORIGINS="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
export OMNIROUTE_AUTO_FREE_FALLBACK_TO_FULL_POOL="true"

# Force enable Browser OAuth & Remote OAuth across all providers
export ALLOW_REMOTE_OAUTH="true"
export ENABLE_REMOTE_OAUTH="true"
export ALLOW_BROWSER_OAUTH="true"
export ENABLE_BROWSER_OAUTH="true"
export DISABLE_LOCAL_OAUTH="false"
export FORCE_PUBLIC_OAUTH="true"
export ALLOW_HEADLESS_OAUTH="true"
export ENABLE_HEADLESS_OAUTH="true"
export OMNIROUTE_ALLOW_BROWSER_OAUTH="true"
export OMNIROUTE_ENABLE_REMOTE_OAUTH="true"
export OAUTH_CALLBACK_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}/api/cloud-agent-credentials/callback"
export NEXT_PUBLIC_OAUTH_CALLBACK_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}/api/cloud-agent-credentials/callback"

# Default admin credentials for OmniRoute
export INITIAL_PASSWORD="${INITIAL_PASSWORD:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
export OMNIROUTE_INITIAL_PASSWORD="${OMNIROUTE_INITIAL_PASSWORD:-admin}"

# CLI Fingerprint & Provider Compatibility Flags
export CLI_COMPAT_ANTIGRAVITY=1
export CLI_COMPAT_GITHUB=1
export CLI_COMPAT_KIMI_CODING=1
export CLI_COMPAT_CLAUDE=1
export CLI_COMPAT_CODEX=1
export CLI_COMPAT_CURSOR=1
export CLI_COMPAT_QWEN=1

# Optional Provider OAuth Client Credentials (loaded from /data/.env or Space Secrets if provided)
export ANTIGRAVITY_OAUTH_CLIENT_ID="${ANTIGRAVITY_OAUTH_CLIENT_ID:-}"
export ANTIGRAVITY_OAUTH_CLIENT_SECRET="${ANTIGRAVITY_OAUTH_CLIENT_SECRET:-}"
export GEMINI_CLI_OAUTH_CLIENT_ID="${GEMINI_CLI_OAUTH_CLIENT_ID:-}"
export GEMINI_CLI_OAUTH_CLIENT_SECRET="${GEMINI_CLI_OAUTH_CLIENT_SECRET:-}"
export GITHUB_OAUTH_CLIENT_ID="${GITHUB_OAUTH_CLIENT_ID:-}"
export KIMI_CODING_OAUTH_CLIENT_ID="${KIMI_CODING_OAUTH_CLIENT_ID:-}"

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
            if [ -f "/root/.omniroute/storage.sqlite" ] && command -v sqlite3 >/dev/null 2>&1; then
                mkdir -p /data/omniroute 2>/dev/null || true
                sqlite3 /root/.omniroute/storage.sqlite ".backup /data/omniroute/storage.sqlite" 2>/dev/null || true
            fi
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
    export WEBUI_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space/openwebui}"
    export OPENAI_API_BASE_URL="http://127.0.0.1:20129/v1"
    export OPENAI_API_KEY="omniroute"
    export WEBUI_SECRET_KEY="$WEBUI_SECRET_KEY"
    export ENABLE_OLLAMA_API="${ENABLE_OLLAMA_API:-false}"
    export ENABLE_OPENAI_API="true"
    export ENABLE_WEBSOCKET_SUPPORT="true"
    export WEBSOCKET_MANAGER="redis"
    export WEBSOCKET_REDIS_URL="redis://127.0.0.1:6379/1"
    export WEBUI_WORKERS=1
    # Disable local PyTorch/SentenceTransformers embedding engine to make Open WebUI lightweight & fast
    export RAG_EMBEDDING_ENGINE=""
    export RAG_EMBEDDING_MODEL=""
    export ENABLE_RAG_HYBRID_SEARCH="false"
    export RAG_AUTO_UPDATE_INDEX="false"
    export TOOL_SERVERS=""
    export OPENAPI_TOOL_SERVERS=""
    export PORT=8098
    export DATA_DIR="/data/open-webui"
    mkdir -p /root/.cache /data/cache /data/open-webui 2>/dev/null || true
    if [ ! -L "/root/.open-webui" ]; then
        rm -rf /root/.open-webui 2>/dev/null || true
        ln -sf /data/open-webui /root/.open-webui
    fi
    export CORS_ALLOW_ORIGIN="https://jishnupg-opencode-cli.hf.space"
    export HF_HUB_ENABLE_HF_TRANSFER="1"
    export WEBUI_AUTH="true"
    export ENABLE_SIGNUP="true"
    open-webui serve --port 8098 --workers 1 &
    echo "[INIT] Open WebUI started in background (PID=$!). Waiting for health..."
    OWUI_HEALTHY=0
    for i in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:8098/health" >/dev/null 2>&1 || curl -fsS "http://127.0.0.1:8098/api/config" >/dev/null 2>&1; then
            echo "[HEALTH] Open WebUI healthy after ${i}s"
            OWUI_HEALTHY=1
            break
        fi
        sleep 1
    done
    if [ "$OWUI_HEALTHY" -eq 0 ]; then
        echo "[WARN] Open WebUI startup check timed out after 30s, proceeding with Gateway startup."
    fi
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
