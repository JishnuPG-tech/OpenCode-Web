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

# Ensure deterministic, permanent secrets and persist to /data/omniroute/server.env
export JWT_SECRET="${JWT_SECRET:-$(echo "opencode_jwt_secret_hf_space_key_2026" | sha256sum | cut -c1-48)}"
export API_KEY_SECRET="${API_KEY_SECRET:-$(echo "opencode_api_key_secret_hf_space_key_2026" | sha256sum | cut -c1-64)}"
export OMNIROUTE_WS_BRIDGE_SECRET="${OMNIROUTE_WS_BRIDGE_SECRET:-$(echo "ws_bridge_${JWT_SECRET}" | sha256sum | cut -c1-48)}"
export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-$(echo "owui_${JWT_SECRET}" | sha256sum | cut -c1-56)}"
export ENCRYPTION_SECRET="${ENCRYPTION_SECRET:-${JWT_SECRET}}"
export OMNIROUTE_SECRET_KEY="${OMNIROUTE_SECRET_KEY:-${JWT_SECRET}}"

mkdir -p /data/omniroute 2>/dev/null || true
if [ ! -f "/data/omniroute/server.env" ]; then
    echo "[INIT] Persisting permanent encryption secrets to /data/omniroute/server.env..."
    cat <<EOF > /data/omniroute/server.env
JWT_SECRET="${JWT_SECRET}"
API_KEY_SECRET="${API_KEY_SECRET}"
OMNIROUTE_WS_BRIDGE_SECRET="${OMNIROUTE_WS_BRIDGE_SECRET}"
WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY}"
ENCRYPTION_SECRET="${ENCRYPTION_SECRET}"
OMNIROUTE_SECRET_KEY="${OMNIROUTE_SECRET_KEY}"
EOF
fi

# Debug: show secret statuses
for _VAR in JWT_SECRET API_KEY_SECRET OMNIROUTE_WS_BRIDGE_SECRET WEBUI_SECRET_KEY; do
    eval _VAL=\$$_VAR
    echo "[INIT] ${_VAR} is configured (${#_VAL} chars)"
done
unset _VAR _VAL

# /data is the persistent HF dataset bucket mount
echo "[INIT] Setting up /data directories..."
mkdir -p /data/open-webui /data/omniroute 2>/dev/null || echo "[WARN] Could not create /data directories"
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log \
          /data/jellyfin/media/Movies /data/jellyfin/media/TVShows 2>/dev/null || true

# ── OmniRoute Database Storage & Dynamic Snapshot Resolution ──────────────────
if [ -L "/root/.omniroute" ]; then
    rm -f /root/.omniroute
fi
mkdir -p /root/.omniroute /data/omniroute 2>/dev/null || true
mkdir -p /root/.omniroute/oauth /root/.omniroute/credentials /root/.omniroute/runtime 2>/dev/null || true
mkdir -p /data/omniroute/oauth /data/omniroute/credentials /data/omniroute/runtime 2>/dev/null || true

echo "[STORAGE] Filesystem mount inspection:"
mount | grep -E 'hf|bucket|data|fuse|nfs' || echo "[STORAGE] /data info: $(df -h /data 2>&1 || true)"

# Search for pre-existing non-empty database snapshot anywhere inside /data
FOUND_DB_PATH=$(find /data -name "storage.sqlite" -type f -size +0c 2>/dev/null | head -n 1 || true)

if [ -n "$FOUND_DB_PATH" ] && [ -f "$FOUND_DB_PATH" ]; then
    _SIZE=$(wc -c < "$FOUND_DB_PATH" 2>/dev/null | tr -d ' \t\n\r' || echo "0")
    echo "[PERSISTENCE] Found persistent snapshot at: ${FOUND_DB_PATH} (${_SIZE} bytes)"
    if command -v sqlite3 >/dev/null 2>&1; then
        _CHK=$(sqlite3 "$FOUND_DB_PATH" "PRAGMA quick_check;" 2>/dev/null || echo "failed")
        echo "[PERSISTENCE] Snapshot integrity: ${_CHK}"
    fi
    cp -f "$FOUND_DB_PATH" /root/.omniroute/storage.sqlite
    echo "[PERSISTENCE] Restored persistent OmniRoute database successfully into /root/.omniroute/storage.sqlite"
else
    echo "[PERSISTENCE] No pre-existing non-empty database found in /data. OmniRoute will start with fresh DB."
fi

# Restore pre-existing OAuth tokens, credentials, runtime files, and server.env if available
for _ITEM in oauth credentials runtime server.env; do
    if [ -e "/data/omniroute/${_ITEM}" ]; then
        cp -af /data/omniroute/${_ITEM} /root/.omniroute/ 2>/dev/null || true
        echo "[PERSISTENCE] Restored persistent OmniRoute state: ${_ITEM}"
    else
        echo "[PERSISTENCE] Initialized empty persistent state directory: ${_ITEM}"
    fi
done

# Continuous sync function (consolidates live ext4 DB & OAuth tokens -> persistent bucket snapshot)
sync_omniroute_db() {
    if [ -f "/root/.omniroute/storage.sqlite" ] && [ -s "/root/.omniroute/storage.sqlite" ]; then
        TARGET_SNAP="/data/omniroute/storage.sqlite"
        if [ -d "/data/omniroute/storage.sqlite" ]; then
            TARGET_SNAP="/data/omniroute/storage.sqlite/storage.sqlite"
        else
            mkdir -p /data/omniroute 2>/dev/null || true
        fi

        if command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 /root/.omniroute/storage.sqlite ".backup ${TARGET_SNAP}" 2>/dev/null || cp -f /root/.omniroute/storage.sqlite "${TARGET_SNAP}" 2>/dev/null || true
        else
            cp -f /root/.omniroute/storage.sqlite "${TARGET_SNAP}" 2>/dev/null || true
        fi

        # Synchronize OAuth token files, credentials, runtime data, and server.env to persistent volume
        for _ITEM in oauth credentials runtime server.env; do
            if [ -e "/root/.omniroute/${_ITEM}" ]; then
                cp -af /root/.omniroute/${_ITEM} /data/omniroute/ 2>/dev/null || true
            fi
        done

        _ACTIVE_SIZE=$(wc -c < /root/.omniroute/storage.sqlite 2>/dev/null | tr -d ' \t\n\r' || echo "0")
        _SNAP_SIZE=$(wc -c < "${TARGET_SNAP}" 2>/dev/null | tr -d ' \t\n\r' || echo "0")
        echo "[PERSISTENCE] Snapshot & OAuth state sync complete: Active DB (${_ACTIVE_SIZE} bytes) -> Persistent Snapshot (${_SNAP_SIZE} bytes)"
    fi
}

# Flush to persistent storage on exit signals
trap sync_omniroute_db EXIT INT TERM

# Background sync loop every 120s (2 minutes)
(
    while true; do
        sleep 120
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
            sync_omniroute_db
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
    # Disable local PyTorch/SentenceTransformers embedding engine to make Open WebUI lightweight & instant
    export BYPASS_EMBEDDING_AND_RETRIEVAL="true"
    export RAG_EMBEDDING_ENGINE=""
    export RAG_EMBEDDING_MODEL=""
    export RAG_RERANKING_MODEL=""
    export ENABLE_RAG_HYBRID_SEARCH="false"
    export ENABLE_RAG_LOCAL_WEB_FETCH="false"
    export RAG_AUTO_UPDATE="false"
    export RAG_AUTO_UPDATE_INDEX="false"
    export ENABLE_VERSION_UPDATE_CHECK="false"
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
    export WEBUI_AUTH="true"
    export ENABLE_SIGNUP="true"
    open-webui serve --port 8098 &
    OWUI_PID=$!
    echo "[INIT] Open WebUI started in background (PID=${OWUI_PID}). Waiting for health..."
    OWUI_HEALTHY=0
    for i in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:8098/health" >/dev/null 2>&1 || curl -fsS "http://127.0.0.1:8098/api/config" >/dev/null 2>&1; then
            echo "[HEALTH] Open WebUI healthy after ${i}s"
            OWUI_HEALTHY=1
            break
        fi
        if ! kill -0 "$OWUI_PID" 2>/dev/null; then
            echo "[ERROR] Open WebUI process (PID=${OWUI_PID}) exited prematurely during startup"
            break
        fi
        sleep 1
    done
    if [ "$OWUI_HEALTHY" -eq 0 ]; then
        echo "[WARN] Open WebUI startup check completed without health confirmation, proceeding with Gateway startup."
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
