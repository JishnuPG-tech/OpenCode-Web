#!/bin/sh

echo "============================================"
echo "=== OpenCode Space Starting Up (Fast Gateway Mode) ==="
echo "Time: $(date)"
echo "============================================"

git config --global --add safe.directory '*' 2>/dev/null || true

START_TIME=$(python3 -c "import time; print(time.time())" 2>/dev/null || echo "0")

get_elapsed() {
    if [ "$START_TIME" != "0" ]; then
        python3 -c "import time; print(f'{time.time() - $START_TIME:.2f}s')" 2>/dev/null || echo "0.0s"
    else
        echo "0.0s"
    fi
}

# ── STEP 1: Master Secret Validation (Must be provided via HF Space Secrets) ─
if [ -z "$STORAGE_ENCRYPTION_KEY" ]; then
    echo "[FATAL ERROR] STORAGE_ENCRYPTION_KEY is not set in environment or HF Space Secrets!"
    echo "[FATAL ERROR] Master encryption key must be provided via Hugging Face Space Secrets to decrypt persistent credentials."
    exit 1
fi

if [ -z "$JWT_SECRET" ]; then
    echo "[FATAL ERROR] JWT_SECRET is not set in environment or HF Space Secrets!"
    echo "[FATAL ERROR] JWT_SECRET is mandatory for system token authentication."
    exit 1
fi

if [ -z "$API_KEY_SECRET" ]; then
    echo "[FATAL ERROR] API_KEY_SECRET is not set in environment or HF Space Secrets!"
    echo "[FATAL ERROR] API_KEY_SECRET is mandatory for API key validation."
    exit 1
fi

if [ -z "$INITIAL_PASSWORD" ]; then
    echo "[FATAL ERROR] INITIAL_PASSWORD is not set in Hugging Face Space Secrets!"
    echo "[FATAL ERROR] INITIAL_PASSWORD is mandatory for OmniRoute authentication."
    exit 1
fi

export ENCRYPTION_SECRET="${STORAGE_ENCRYPTION_KEY}"
export OMNIROUTE_SECRET_KEY="${STORAGE_ENCRYPTION_KEY}"
export OMNIROUTE_WS_BRIDGE_SECRET="${OMNIROUTE_WS_BRIDGE_SECRET:-$(echo "ws_bridge_${JWT_SECRET}" | sha256sum | cut -c1-48)}"
export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-$(echo "owui_${JWT_SECRET}" | sha256sum | cut -c1-56)}"

# Purge any legacy secret env files from storage bucket to maintain strict secret separation
rm -f /data/.env /data/secrets.env /data/secrets /data/config/.env /data/omniroute/.env /data/omniroute/secrets.env /data/omniroute/secrets /data/omniroute/.secrets /data/omniroute/server.env 2>/dev/null || true

echo "[BOOT] Secrets validated: $(get_elapsed)"

# ── STEP 2: Directory Model & SQLite Snapshot Restoration ─────────────────────
PERSIST_DIR="/data/omniroute"
PERSIST_DB="/data/omniroute/storage.sqlite"
BACKUP_DIR="/data/omniroute/backups"

RUNTIME_DIR="/root/.omniroute"
RUNTIME_DB="/root/.omniroute/storage.sqlite"

if [ -d "$PERSIST_DB" ]; then
    rm -rf "$PERSIST_DB" 2>/dev/null || true
fi

mkdir -p "$PERSIST_DIR" "$BACKUP_DIR" "$RUNTIME_DIR" 2>/dev/null || true

if [ -f "$PERSIST_DB" ] && [ -s "$PERSIST_DB" ]; then
    _INIT_SIZE=$(wc -c < "$PERSIST_DB" 2>/dev/null | tr -d ' \t\n\r' || echo "0")
    echo "[PERSISTENCE] Found OmniRoute snapshot at: ${PERSIST_DB} (${_INIT_SIZE} bytes)"
    if command -v sqlite3 >/dev/null 2>&1; then
        _CHK=$(sqlite3 "$PERSIST_DB" "PRAGMA quick_check;" 2>/dev/null || echo "failed")
        if [ "$_CHK" = "ok" ]; then
            cp -f "$PERSIST_DB" "$RUNTIME_DB"
            echo "[PERSISTENCE] Restored persistent database into ${RUNTIME_DB} successfully."
        else
            echo "[PERSISTENCE] WARNING: Persistent snapshot failed integrity check. Initializing fresh runtime DB."
        fi
    else
        cp -f "$PERSIST_DB" "$RUNTIME_DB"
        echo "[PERSISTENCE] Restored persistent database into ${RUNTIME_DB}."
    fi
fi

# One-time targeted cleanup: remove credential rows that fail to decrypt
if [ -f "$RUNTIME_DB" ] && command -v python3 >/dev/null 2>&1; then
    python3 - "$RUNTIME_DB" <<'PYEOF' 2>&1 || true
import sqlite3, sys
db_path = sys.argv[1]
BROKEN_PREFIXES = (
    "enc:v1:c8b287e6f9ea4dc7a3d5ccd",
    "enc:v1:003964800c0b7803fa74504",
    "enc:v1:8d5ca7d6f541555ed9692a7",
    "enc:v1:d905a9b8be117264d2caaee",
    "enc:v1:076a2b5e61f84d7dbd9d418",
    "enc:v1:ae5a4040c5f73dd42429d7c",
)
try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cur.fetchall()]
    deleted_total = 0
    for table in tables:
        cur.execute(f"PRAGMA table_info({table});")
        cols = [c[1] for c in cur.fetchall()]
        text_cols = [c for c in cols if c.lower() in
                     ("encrypted_value", "value", "token", "credential",
                      "access_token", "refresh_token", "data", "secret")]
        for col in text_cols:
            for prefix in BROKEN_PREFIXES:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE {col} LIKE ?", (prefix + "%",))
                    if cur.rowcount > 0:
                        deleted_total += cur.rowcount
                except sqlite3.OperationalError:
                    pass
    conn.commit()
    conn.close()
    if deleted_total:
        print(f"[CLEANUP] Removed {deleted_total} unrecoverable credential row(s) total.")
except Exception as e:
    pass
PYEOF
fi

# Restore supplementary state directories
for _ITEM in oauth credentials runtime gemini_cli config_dir; do
    if [ -d "${PERSIST_DIR}/${_ITEM}" ]; then
        if [ "$_ITEM" = "gemini_cli" ]; then
            mkdir -p /root/.gemini 2>/dev/null || true
            cp -af "${PERSIST_DIR}/gemini_cli/"* /root/.gemini/ 2>/dev/null || true
        elif [ "$_ITEM" = "config_dir" ]; then
            mkdir -p /root/.config 2>/dev/null || true
            cp -af "${PERSIST_DIR}/config_dir/"* /root/.config/ 2>/dev/null || true
        else
            mkdir -p "${RUNTIME_DIR}/${_ITEM}" 2>/dev/null || true
            cp -af "${PERSIST_DIR}/${_ITEM}/"* "${RUNTIME_DIR}/${_ITEM}/" 2>/dev/null || true
        fi
    fi
done

# Database WAL Backup Synchronization Function
sync_omniroute_db() {
    if [ -f "$RUNTIME_DB" ] && [ -s "$RUNTIME_DB" ]; then
        mkdir -p "$PERSIST_DIR" "$BACKUP_DIR" 2>/dev/null || true
        if command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 "$RUNTIME_DB" ".backup '$PERSIST_DB'" 2>/dev/null || cp -f "$RUNTIME_DB" "$PERSIST_DB" 2>/dev/null || true
        else
            cp -f "$RUNTIME_DB" "$PERSIST_DB" 2>/dev/null || true
        fi

        _CHK="ok"
        if command -v sqlite3 >/dev/null 2>&1; then
            _CHK=$(sqlite3 "$PERSIST_DB" "PRAGMA quick_check;" 2>/dev/null || echo "failed")
        fi

        if [ "$_CHK" = "ok" ]; then
            cp -f "$PERSIST_DB" "${BACKUP_DIR}/last-known-good.sqlite" 2>/dev/null || true
            TIMESTAMP=$(date +%Y%m%d-%H%M)
            cp -f "$PERSIST_DB" "${BACKUP_DIR}/storage-${TIMESTAMP}.sqlite" 2>/dev/null || true
            ls -t "${BACKUP_DIR}"/storage-*.sqlite 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true
            
            for _ITEM in oauth credentials runtime; do
                if [ -d "${RUNTIME_DIR}/${_ITEM}" ]; then
                    mkdir -p "${PERSIST_DIR}/${_ITEM}" 2>/dev/null || true
                    cp -af "${RUNTIME_DIR}/${_ITEM}/"* "${PERSIST_DIR}/${_ITEM}/" 2>/dev/null || true
                fi
            done

            if [ -d "/root/.gemini" ]; then
                mkdir -p "${PERSIST_DIR}/gemini_cli" 2>/dev/null || true
                cp -af /root/.gemini/* "${PERSIST_DIR}/gemini_cli/" 2>/dev/null || true
            fi

            if [ -d "/root/.config" ]; then
                mkdir -p "${PERSIST_DIR}/config_dir" 2>/dev/null || true
                cp -af /root/.config/* "${PERSIST_DIR}/config_dir/" 2>/dev/null || true
            fi
            _SIZE=$(wc -c < "$PERSIST_DB" 2>/dev/null | tr -d ' \t\n\r' || echo "0")
            echo "[PERSISTENCE] Snapshot OK: ${_SIZE} bytes synced to ${PERSIST_DB}"
        fi
    fi
}

trap sync_omniroute_db EXIT INT TERM

# ── STEP 3: Start FastAPI Gateway Immediately ────────────────────────────────
echo "[BOOT] FastAPI starting: $(get_elapsed)"
cd /
python3 -m uvicorn proxy:app --host 127.0.0.1 --port 8000 --workers 2 &
GATEWAY_PID=$!

for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:8000/health/live" >/dev/null 2>&1; then
        echo "[BOOT] FastAPI live: $(get_elapsed)"
        break
    fi
    if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
        echo "[ERROR] FastAPI Gateway exited prematurely during startup"
        exit 1
    fi
    sleep 0.1
done

# ── STEP 4: Start NGINX Edge Proxy Immediately ────────────────────────────────
echo "[BOOT] Nginx starting: $(get_elapsed)"
if command -v nginx >/dev/null 2>&1; then
    nginx -t 2>&1 || echo "[WARN] NGINX configuration test warning"
    nginx -g 'daemon off;' &
    NGINX_PID=$!
elif [ -f "/usr/sbin/nginx" ]; then
    /usr/sbin/nginx -t 2>&1 || echo "[WARN] NGINX configuration test warning"
    /usr/sbin/nginx -g 'daemon off;' &
    NGINX_PID=$!
else
    echo "[WARN] NGINX binary not found. Binding FastAPI Gateway directly to 4096..."
    kill "$GATEWAY_PID" 2>/dev/null || true
    exec python3 -m uvicorn proxy:app --host 0.0.0.0 --port 4096 --workers 2
fi

for i in $(seq 1 30); do
    if curl -fsS --max-time 5 "http://127.0.0.1:4096/health/live" >/dev/null 2>&1; then
        echo "[BOOT] Public gateway live: $(get_elapsed)"
        echo "[PROCESS] PID 1: $$"
        echo "[PROCESS] Nginx: PID $NGINX_PID"
        echo "[PROCESS] FastAPI: PID $GATEWAY_PID"
        echo "============================================"
        echo "=== Hugging Face Readiness: PASS (Space RUNNING) ==="
        echo "============================================"
        break
    fi
    if ! kill -0 "$NGINX_PID" 2>/dev/null; then
        echo "[FATAL] Public gateway health check failed: NGINX exited prematurely"
        exit 1
    fi
    sleep 0.1
done

# ── STEP 5: Launch Asynchronous Background Services ──────────────────────────
echo "[BOOT] Background services starting..."
(
    # 1. Start Redis
    echo "[INIT] Starting Redis server on port 6379..."
    redis-server --daemonize yes --bind 127.0.0.1 --port 6379 2>/dev/null || true

    # 2. Start OmniRoute AI Gateway
    echo "[INIT] Starting OmniRoute AI Gateway (Dashboard: 20128, API: 20129, WS: 20132)..."
    export PORT=20128
    export API_PORT=20129
    export LIVE_WS_PORT=20132
    export HOSTNAME="127.0.0.1"
    export DATA_DIR="/root/.omniroute"
    export REDIS_URL="redis://127.0.0.1:6379"
    export NEXT_PUBLIC_BASE_URL="https://jishnupg-opencode-cli.hf.space"
    export AUTH_COOKIE_SECURE="true"
    export ALLOW_REMOTE_OAUTH="true"
    export ALLOW_BROWSER_OAUTH="true"
    export OAUTH_CALLBACK_URL="https://jishnupg-opencode-cli.hf.space/callback"
    export NEXT_PUBLIC_OAUTH_CALLBACK_URL="https://jishnupg-opencode-cli.hf.space/callback"
    export REDIRECT_URI="https://jishnupg-opencode-cli.hf.space/callback"
    export ANTIGRAVITY_OAUTH_REDIRECT_URI="https://jishnupg-opencode-cli.hf.space/callback"
    export ANTIGRAVITY_REDIRECT_URI="https://jishnupg-opencode-cli.hf.space/callback"
    export ADMIN_PASSWORD="$INITIAL_PASSWORD"
    export OMNIROUTE_INITIAL_PASSWORD="$INITIAL_PASSWORD"
    export OMNIROUTE_PASSWORD="$INITIAL_PASSWORD"
    export PASSWORD="$INITIAL_PASSWORD"
    export RESET_PASSWORD="$INITIAL_PASSWORD"
    export OMNIROUTE_RESET_PASSWORD="$INITIAL_PASSWORD"
    export CLI_COMPAT_ANTIGRAVITY=1
    export CLI_COMPAT_GITHUB=1
    export CLI_COMPAT_KIMI_CODING=1
    export CLI_COMPAT_CLAUDE=1
    export CLI_COMPAT_CODEX=1
    export CLI_COMPAT_CURSOR=1
    export CLI_COMPAT_QWEN=1
    export ANTIGRAVITY_OAUTH_CLIENT_ID="${ANTIGRAVITY_OAUTH_CLIENT_ID:-}"
    export ANTIGRAVITY_OAUTH_CLIENT_SECRET="${ANTIGRAVITY_OAUTH_CLIENT_SECRET:-}"
    export GEMINI_CLI_OAUTH_CLIENT_ID="${GEMINI_CLI_OAUTH_CLIENT_ID:-}"
    export GEMINI_CLI_OAUTH_CLIENT_SECRET="${GEMINI_CLI_OAUTH_CLIENT_SECRET:-}"
    export GITHUB_OAUTH_CLIENT_ID="${GITHUB_OAUTH_CLIENT_ID:-}"
    export KIMI_CODING_OAUTH_CLIENT_ID="${KIMI_CODING_OAUTH_CLIENT_ID:-}"

    if [ -d "/omniroute" ]; then
        cd /omniroute
        if [ -f "server.js" ]; then
            node server.js &
        else
            npm run start -- --port 20128 &
        fi
        OMNIROUTE_PID=$!
        for i in $(seq 1 90); do
            if curl -fsS "http://127.0.0.1:20128/api/monitoring/health" >/dev/null 2>&1; then
                echo "[HEALTH] OmniRoute ready after ${i}s"
                echo "[PROCESS] OmniRoute: PID ${OMNIROUTE_PID}"
                sync_omniroute_db
                break
            fi
            sleep 1
        done
    fi

    # 3. Start Telegram Direct Stream Proxy
    echo "[INIT] Starting Telegram Direct Stream Proxy on port 8080..."
    python3 /tg_streamer.py &
    TG_PID=$!
    echo "[PROCESS] Telegram: PID ${TG_PID}"

    # 4. Start Jellyfin Media Server
    echo "[INIT] Starting Jellyfin Media Server on port 8096..."
    WEBDIR_OPT=""
    if [ -d "/usr/share/jellyfin/web" ]; then
        WEBDIR_OPT="--webdir /usr/share/jellyfin/web"
    fi
    if command -v jellyfin >/dev/null 2>&1; then
        jellyfin --datadir /data/jellyfin/data --configdir /data/jellyfin/config \
                 --cachedir /data/jellyfin/cache --logdir /data/jellyfin/log $WEBDIR_OPT &
        JELLYFIN_PID=$!
        echo "[PROCESS] Jellyfin: PID ${JELLYFIN_PID}"
    elif [ -f "/usr/bin/jellyfin" ]; then
        /usr/bin/jellyfin --datadir /data/jellyfin/data --configdir /data/jellyfin/config \
                          --cachedir /data/jellyfin/cache --logdir /data/jellyfin/log $WEBDIR_OPT &
        JELLYFIN_PID=$!
        echo "[PROCESS] Jellyfin: PID ${JELLYFIN_PID}"
    fi

    # 5. Start Open WebUI
    echo "[INIT] Starting Open WebUI on port 8098..."
    if command -v open-webui >/dev/null 2>&1; then
        export WEBUI_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
        export OPENAI_API_BASE_URL="http://127.0.0.1:20129/v1"
        export OPENAI_API_KEY="omniroute"
        export WEBUI_SECRET_KEY="$WEBUI_SECRET_KEY"
        export ENABLE_OLLAMA_API="${ENABLE_OLLAMA_API:-false}"
        export ENABLE_OPENAI_API="true"
        export ENABLE_WEBSOCKET_SUPPORT="true"
        export WEBSOCKET_MANAGER="redis"
        export WEBSOCKET_REDIS_URL="redis://127.0.0.1:6379/1"
        export WEBUI_WORKERS=1
        export BYPASS_EMBEDDING_AND_RETRIEVAL="true"
        export RAG_EMBEDDING_ENGINE=""
        export RAG_EMBEDDING_MODEL="none"
        export VECTOR_DB_EMBEDDING_FUNCTION="none"
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
        echo "[PROCESS] Open WebUI: PID ${OWUI_PID}"
        for i in $(seq 1 60); do
            if curl -fsS "http://127.0.0.1:8098/health" >/dev/null 2>&1 || curl -fsS "http://127.0.0.1:8098/api/config" >/dev/null 2>&1; then
                echo "[HEALTH] Open WebUI ready after ${i}s"
                break
            fi
            sleep 1
        done
    fi

    # 6. Background 120s Backup Loop
    while true; do
        sleep 120
        sync_omniroute_db
    done
) &

# ── STEP 6: Maintain Container Process Lifetime ──────────────────────────────
wait "$NGINX_PID"
