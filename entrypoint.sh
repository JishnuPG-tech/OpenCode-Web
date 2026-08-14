#!/bin/sh
set -e

START_TIME=$(date +%s)
get_elapsed() {
    if [ -n "$START_TIME" ]; then
        python3 -c "import time; print(f'{time.time() - $START_TIME:.2f}s')" 2>/dev/null || echo "0.0s"
    else
        echo "0.0s"
    fi
}

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
mkdir -p /data/hermes/memories /data/hermes/skills /data/hermes/sessions 2>/dev/null || true
mkdir -p /root/.cache /data/cache /root/.hermes/memories /root/.hermes/skills 2>/dev/null || true
chmod -R 777 /root/.cache /data/cache /data/hermes 2>/dev/null || true

# ── STEP 1: Master Secret Validation ──────────────────────────────────────────
if [ -z "$STORAGE_ENCRYPTION_KEY" ]; then
    echo "[WARN] STORAGE_ENCRYPTION_KEY is not set in secrets; using local fallback."
    export STORAGE_ENCRYPTION_KEY="omniroute_default_storage_key_32bytes"
fi

if [ -z "$JWT_SECRET" ]; then
    echo "[WARN] JWT_SECRET is not set in secrets; using local fallback."
    export JWT_SECRET="omniroute_default_jwt_secret_key_32bytes"
fi

if [ -z "$API_KEY_SECRET" ]; then
    echo "[WARN] API_KEY_SECRET is not set in secrets; using local fallback."
    export API_KEY_SECRET="omniroute_default_api_key_secret_32bytes"
fi

if [ -z "$INITIAL_PASSWORD" ]; then
    echo "[WARN] INITIAL_PASSWORD is not set in secrets; using local fallback."
    export INITIAL_PASSWORD="admin123"
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

PERSIST_WEBUI_DIR="/data/open-webui"
PERSIST_WEBUI_DB="/data/open-webui/webui.db"
RUNTIME_WEBUI_DIR="/root/.open-webui"
RUNTIME_WEBUI_DB="/root/.open-webui/webui.db"

if [ -d "$PERSIST_DB" ]; then
    rm -rf "$PERSIST_DB" 2>/dev/null || true
fi

mkdir -p "$PERSIST_DIR" "$BACKUP_DIR" "$RUNTIME_DIR" "$PERSIST_WEBUI_DIR" "$RUNTIME_WEBUI_DIR" 2>/dev/null || true

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

if [ -f "$PERSIST_WEBUI_DB" ] && [ -s "$PERSIST_WEBUI_DB" ]; then
    _WEBUI_SIZE=$(wc -c < "$PERSIST_WEBUI_DB" 2>/dev/null | tr -d ' \t\n\r' || echo "0")
    echo "[PERSISTENCE] Found Open WebUI snapshot at: ${PERSIST_WEBUI_DB} (${_WEBUI_SIZE} bytes)"
    if command -v sqlite3 >/dev/null 2>&1; then
        _WCHK=$(sqlite3 "$PERSIST_WEBUI_DB" "PRAGMA quick_check;" 2>/dev/null || echo "failed")
        if [ "$_WCHK" = "ok" ]; then
            cp -f "$PERSIST_WEBUI_DB" "$RUNTIME_WEBUI_DB" 2>/dev/null || true
            echo "[PERSISTENCE] Restored persistent Open WebUI database into ${RUNTIME_WEBUI_DB} successfully."
        fi
    else
        cp -f "$PERSIST_WEBUI_DB" "$RUNTIME_WEBUI_DB" 2>/dev/null || true
        echo "[PERSISTENCE] Restored persistent Open WebUI database into ${RUNTIME_WEBUI_DB}."
    fi
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
            sqlite3 "$RUNTIME_DB" "PRAGMA wal_checkpoint(PASSIVE);" 2>/dev/null || true
            sqlite3 "$RUNTIME_DB" ".backup '$PERSIST_DB'" 2>/dev/null || cp -f "$RUNTIME_DB" "$PERSIST_DB" 2>/dev/null || true
        else
            cp -f "$RUNTIME_DB" "$PERSIST_DB" 2>/dev/null || true
        fi
        [ -f "${RUNTIME_DB}-wal" ] && cp -f "${RUNTIME_DB}-wal" "${PERSIST_DB}-wal" 2>/dev/null || true
        [ -f "${RUNTIME_DB}-shm" ] && cp -f "${RUNTIME_DB}-shm" "${PERSIST_DB}-shm" 2>/dev/null || true

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

    # Synchronize Open WebUI database safely if active
    for _SRC_WDB in "$PERSIST_WEBUI_DB" "$RUNTIME_WEBUI_DB" "/data/open-webui/data/webui.db"; do
        if [ -f "$_SRC_WDB" ] && [ -s "$_SRC_WDB" ]; then
            _R_SRC=$(python3 -c "import os; print(os.path.realpath('$_SRC_WDB'))" 2>/dev/null || echo "$_SRC_WDB")
            _R_DST=$(python3 -c "import os; print(os.path.realpath('$PERSIST_WEBUI_DB'))" 2>/dev/null || echo "$PERSIST_WEBUI_DB")
            
            if [ "$_R_SRC" != "$_R_DST" ]; then
                if command -v sqlite3 >/dev/null 2>&1; then
                    sqlite3 "$_SRC_WDB" ".backup '$PERSIST_WEBUI_DB'" 2>/dev/null || cp -f "$_SRC_WDB" "$PERSIST_WEBUI_DB" 2>/dev/null || true
                else
                    cp -f "$_SRC_WDB" "$PERSIST_WEBUI_DB" 2>/dev/null || true
                fi
            fi
            _WSIZE=$(wc -c < "$PERSIST_WEBUI_DB" 2>/dev/null | tr -d ' \t\n\r' || echo "0")
            echo "[PERSISTENCE] Open WebUI DB snapshot OK: ${_WSIZE} bytes present at ${PERSIST_WEBUI_DB}"
            break
        fi
    done
}

trap sync_omniroute_db EXIT INT TERM

# ── STEP 3: Start FastAPI Gateway Immediately ────────────────────────────────
echo "[BOOT] FastAPI starting: $(get_elapsed)"
cd /
python3 -m uvicorn proxy:app --host 127.0.0.1 --port 8000 --workers 2 &
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

    # Step 8: Start Redis Server & OmniRoute AI Gateway in Background
    if command -v redis-server >/dev/null 2>&1; then
        echo "[INIT] Starting Redis server on port 6379..."
        redis-server --daemonize yes 2>/dev/null || true
    fi

    echo "[INIT] Starting OmniRoute AI Gateway..."
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
    export OMNIROUTE_AUTO_FREE_FALLBACK_TO_FULL_POOL=true
    export OMNIROUTE_ALLOW_UNAUTHENTICATED=true

    if [ -d "/omniroute" ]; then
        cd /omniroute
        if [ -f "/fix_omniroute.py" ]; then
            python3 /fix_omniroute.py /omniroute 2>&1 || true
        elif [ -f "fix_omniroute.py" ]; then
            python3 fix_omniroute.py ./ 2>&1 || true
        fi
        if [ -f "server.js" ]; then
            node server.js &
        else
            npm run start -- --port 20128 &
        fi
        OMNIROUTE_PID=$!
        (
            for i in $(seq 1 90); do
                if curl -fsS "http://127.0.0.1:20128/api/monitoring/health" >/dev/null 2>&1; then
                    echo "[HEALTH] OmniRoute ready after ${i}s"
                    echo "[PROCESS] OmniRoute: PID ${OMNIROUTE_PID}"
                    sync_omniroute_db
                    break
                fi
                sleep 1
            done
        ) &
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
    mkdir -p /root/.open-webui /data/open-webui /data/cache 2>/dev/null || true
    if [ -f "/data/open-webui/webui.db" ] && ! [ -s "/data/open-webui/webui.db" ]; then
        rm -f /data/open-webui/webui.db 2>/dev/null || true
    fi
    if [ -f "/data/open-webui/webui.db" ] && [ -s "/data/open-webui/webui.db" ]; then
        mkdir -p /root/.open-webui/data 2>/dev/null || true
        cp -f /data/open-webui/webui.db /root/.open-webui/webui.db 2>/dev/null || true
        cp -f /data/open-webui/webui.db /root/.open-webui/data/webui.db 2>/dev/null || true
        echo "[PERSISTENCE] Restored Open WebUI database snapshot ($(wc -c < /data/open-webui/webui.db | tr -d ' ') bytes)."
    fi

    # Clean up legacy RAG embedding model 'none' from webui.db if present
    python3 -c "
import sqlite3, json
for path in ['/root/.open-webui/webui.db', '/root/.open-webui/data/webui.db', '/data/open-webui/webui.db']:
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, data FROM config WHERE id = \"rag\"')
        row = cursor.fetchone()
        if row:
            data = json.loads(row[1])
            if data.get('embedding_model') == 'none':
                data['embedding_model'] = ''
            if data.get('embedding_engine') == 'none':
                data['embedding_engine'] = ''
            cursor.execute('UPDATE config SET data = ? WHERE id = \"rag\"', (json.dumps(data),))
            conn.commit()
            print(f'[FIX] Cleaned RAG config in {path}')
        conn.close()
    except Exception:
        pass
" 2>/dev/null || true

    # 5. Start Open WebUI
    echo "[INIT] Starting Open WebUI on port 8098..."
    if command -v open-webui >/dev/null 2>&1; then
        FOUND_BUILD_DIR=$(python3 -c "import open_webui, os; pkg=os.path.dirname(open_webui.__file__); matches=[root for root, dirs, files in os.walk(pkg) if 'index.html' in files]; print(matches[0] if matches else '')" 2>/dev/null || echo "")
        if [ -n "$FOUND_BUILD_DIR" ] && [ -d "$FOUND_BUILD_DIR" ]; then
            mkdir -p /root/.open-webui/static 2>/dev/null || true
            cp -rn "$FOUND_BUILD_DIR/"* /root/.open-webui/static/ 2>/dev/null || true
            export BUILD_DIR="$FOUND_BUILD_DIR"
            export FRONTEND_BUILD_DIR="$FOUND_BUILD_DIR"
            export WEBUI_BUILD_DIR="$FOUND_BUILD_DIR"
            export STATIC_DIR="/root/.open-webui/static"
            echo "[INIT] Open WebUI BUILD_DIR auto-located & pinned to: $FOUND_BUILD_DIR"
        fi

        export WEBUI_URL="${WEBUI_URL:-https://jishnupg-opencode-cli.hf.space}"
        export OPENAI_API_BASE_URL="${OPENAI_API_BASE_URL:-http://127.0.0.1:8000/v1}"
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
        export RAG_EMBEDDING_MODEL=""
        export VECTOR_DB_EMBEDDING_FUNCTION=""
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
        unset DATABASE_URL 2>/dev/null || true
        export WEBUI_AUTH="true"
        export ENABLE_SIGNUP="true"
        mkdir -p /root/.cache /data/cache /data/open-webui /root/.open-webui 2>/dev/null || true
        if [ -d "/data/open-webui/webui.db" ]; then
            rm -rf "/data/open-webui/webui.db" 2>/dev/null || true
        fi
        if [ ! -f "/data/open-webui/webui.db" ]; then
            touch "/data/open-webui/webui.db" 2>/dev/null || true
        fi
        chmod -R 777 /data/open-webui /root/.open-webui 2>/dev/null || true
        export CORS_ALLOW_ORIGIN="https://jishnupg-opencode-cli.hf.space"
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
fi

# Start Periodic 15s Database Persistence Backup Daemon
(
    while true; do
        sleep 15
        sync_omniroute_db >/dev/null 2>&1 || true
        for _DB in "/root/.open-webui/webui.db" "/root/.open-webui/data/webui.db"; do
            if [ -f "$_DB" ] && [ -s "$_DB" ]; then
                mkdir -p /data/open-webui 2>/dev/null || true
                cp -f "$_DB" /data/open-webui/webui.db 2>/dev/null || true
                _WEBUI_DB_SIZE=$(wc -c < "/data/open-webui/webui.db" 2>/dev/null | tr -d ' \t\n\r' || echo "0")
                echo "[PERSISTENCE] Open WebUI DB snapshot OK: ${_WEBUI_DB_SIZE} bytes synced from ${_DB} to /data/open-webui/webui.db"
            fi
        done
        # Sync Hermes persistent memory, skills, sessions, SQLite DB
        if [ -d "/root/.hermes" ]; then
            mkdir -p /data/hermes/memories /data/hermes/skills /data/hermes/sessions 2>/dev/null || true
            rsync -a --update /root/.hermes/. /data/hermes/ 2>/dev/null || \
                cp -rf /root/.hermes/. /data/hermes/ 2>/dev/null || true
            _HERMES_SIZE=$(du -sh /data/hermes 2>/dev/null | cut -f1 || echo "?")
            echo "[PERSISTENCE] Hermes snapshot OK: ${_HERMES_SIZE} synced to /data/hermes"
        fi
    done
) &

# Step 12: Start Hermes Agent in Background (Port 8642)
if command -v hermes >/dev/null 2>&1; then
    echo "[HEALTH] Hermes Agent starting in background on port 8642..."
    mkdir -p /data/hermes/memories /data/hermes/skills /data/hermes/sessions 2>/dev/null || true
    chmod -R 777 /data/hermes 2>/dev/null || true
    # Restore persistent Hermes memory from /data volume on boot
    if [ -d "/data/hermes" ] && [ "$(ls -A /data/hermes 2>/dev/null)" ]; then
        rsync -a /data/hermes/. /root/.hermes/ 2>/dev/null || \
            cp -rf /data/hermes/. /root/.hermes/ 2>/dev/null || true
        echo "[PERSISTENCE] Restored Hermes memory from /data/hermes"
    fi
    # Configure Hermes to use OmniRoute as its LLM backend & enable API server
    export HERMES_API_BASE_URL="http://127.0.0.1:20129/v1"
    export HERMES_API_KEY="omniroute"
    export OPENAI_API_BASE="http://127.0.0.1:20129/v1"
    export OPENAI_API_KEY="omniroute"
    export HERMES_MODEL="${HERMES_MODEL:-default}"
    export HERMES_DATA_DIR="/root/.hermes"
    export HERMES_GATEWAY_PORT=8642
    export HERMES_PORT=8642
    export PORT=8642
    export API_SERVER_ENABLED=true
    export API_SERVER_PORT=8642
    export API_SERVER_HOST=127.0.0.1
    export API_SERVER_KEY="${HERMES_GATEWAY_API_KEY:-${HERMES_API_KEY_SECRET:-${API_KEY_SECRET:-${INITIAL_PASSWORD:-hermes_secret_key}}}}"
    export HERMES_GATEWAY_API_KEY="${API_SERVER_KEY}"
    export HERMES_GATEWAY_ENABLED=true

    # Pre-create /root/.hermes/.env file for hermes-agent
    cat > /root/.hermes/.env << HERMES_ENV
API_SERVER_ENABLED=true
API_SERVER_PORT=8642
API_SERVER_HOST=127.0.0.1
API_SERVER_KEY=${API_SERVER_KEY}
OPENAI_API_BASE=http://127.0.0.1:20129/v1
OPENAI_API_BASE_URL=http://127.0.0.1:20129/v1
OPENAI_API_KEY=omniroute
HERMES_API_BASE_URL=http://127.0.0.1:20129/v1
HERMES_API_KEY=omniroute
DEFAULT_MODEL=${HERMES_MODEL}
TELEGRAM_ENABLED=${TELEGRAM_BOT_TOKEN:+true}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_ALLOW_ALL_USERS=true
TELEGRAM_ALLOWED_USERS=${TELEGRAM_ALLOWED_USERS:-*}
HERMES_ENV

    # Pre-create Hermes config.json pointing to OmniRoute so no interactive setup is needed
    cat > /root/.hermes/config.json << HERMES_CFG
{
  "api_base_url": "http://127.0.0.1:20129/v1",
  "api_key": "omniroute",
  "model": "${HERMES_MODEL}",
  "data_dir": "/root/.hermes",
  "api_server": {
    "enabled": true,
    "port": 8642,
    "host": "127.0.0.1",
    "key": "${API_SERVER_KEY}"
  },
  "gateway": {
    "enabled": true,
    "port": 8642,
    "api_key": "${API_SERVER_KEY}"
  },
  "memory": {
    "enabled": true,
    "sqlite_fts5": true,
    "memory_file": "/root/.hermes/memories/MEMORY.md",
    "user_file": "/root/.hermes/memories/USER.md"
  },
  "tools": {
    "web_search": true,
    "web_extract": true,
    "browser_automation": true
  }
}
HERMES_CFG

    # Restore repository hermes_config.yaml if present
    if [ -f "/app/hermes_config.yaml" ]; then
        cp /app/hermes_config.yaml /root/.hermes/config.yaml
        echo "[HERMES] Restored repository hermes_config.yaml -> /root/.hermes/config.yaml"
    elif [ -f "./hermes_config.yaml" ]; then
        cp ./hermes_config.yaml /root/.hermes/config.yaml
        echo "[HERMES] Restored ./hermes_config.yaml -> /root/.hermes/config.yaml"
    fi
    echo "[HERMES] Config & .env written: OmniRoute -> http://127.0.0.1:20129/v1, model=${HERMES_MODEL}, API_SERVER_PORT=8642"

    # Configure Telegram bot integration if token is provided
    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        export HERMES_TELEGRAM_TOKEN="$TELEGRAM_BOT_TOKEN"
        export HERMES_TELEGRAM_ENABLED=true
        export TELEGRAM_ALLOW_ALL_USERS=true
        export TELEGRAM_ALLOWED_USERS="${TELEGRAM_ALLOWED_USERS:-*}"
        python3 -c "
import json
try:
    cfg = json.load(open('/root/.hermes/config.json'))
    cfg['telegram'] = {
        'enabled': True,
        'token': '${TELEGRAM_BOT_TOKEN}',
        'allow_all_users': True,
        'allowed_users': ['*']
    }
    json.dump(cfg, open('/root/.hermes/config.json', 'w'), indent=2)
    print('[HERMES] Telegram bot & user authorization injected into config')
except Exception as e:
    print(f'[HERMES] Telegram config inject warning: {e}')
" 2>/dev/null || true
        echo "[HERMES] Telegram bot integration & user authorization enabled"
    fi

    # Detect the correct hermes CLI command for the installed version
    echo "[HERMES] Detecting available commands..."
    hermes --help > /data/cache/hermes_help.log 2>&1 || true
    cat /data/cache/hermes_help.log | head -20 | sed 's/^/[HERMES-HELP] /' || true

    HERMES_START_CMD=""
    if hermes gateway --help >/dev/null 2>&1; then
        HERMES_START_CMD="hermes gateway"
        echo "[HERMES] Using command: hermes gateway"
    elif hermes gateway run --help >/dev/null 2>&1; then
        HERMES_START_CMD="hermes gateway run"
        echo "[HERMES] Using command: hermes gateway run"
    elif hermes serve --help >/dev/null 2>&1; then
        HERMES_START_CMD="hermes serve"
        echo "[HERMES] Using command: hermes serve"
    elif hermes start --help >/dev/null 2>&1; then
        HERMES_START_CMD="hermes start"
        echo "[HERMES] Using command: hermes start"
    elif hermes api --help >/dev/null 2>&1; then
        HERMES_START_CMD="hermes api"
        echo "[HERMES] Using command: hermes api"
    else
        echo "[HERMES] WARNING: No gateway command found. Available commands logged to /data/cache/hermes_help.log"
    fi

    if [ -n "$HERMES_START_CMD" ]; then
        # Pipe to BOTH log file and stdout so errors are visible in Space logs
        $HERMES_START_CMD 2>&1 | tee /data/cache/hermes.log | sed 's/^/[HERMES] /' &
        HERMES_PID=$!
        echo "[PROCESS] Hermes Agent: PID ${HERMES_PID}"
        for i in $(seq 1 30); do
            if ! kill -0 $HERMES_PID 2>/dev/null; then
                echo "[HERMES] ERROR: Process died immediately. Last lines:"
                tail -20 /data/cache/hermes.log 2>/dev/null | sed 's/^/[HERMES-ERR] /' || true
                HERMES_PID=""
                break
            fi
            if curl -fsS "http://127.0.0.1:8642/health" >/dev/null 2>&1 || \
               curl -fsS "http://127.0.0.1:8642/v1/models" >/dev/null 2>&1; then
                echo "[HEALTH] Hermes Agent ready after ${i}s"
                break
            fi
            sleep 1
        done
    fi
fi

# Step 12 & 13: Keep PID 1 Alive and Monitor Child Processes
echo "[BOOT] All services dispatched. Process Supervisor active."

while true; do
    if [ -n "$FASTAPI_PID" ] && ! kill -0 $FASTAPI_PID 2>/dev/null; then
        echo "[CRITICAL] FastAPI Gateway process died! Restarting..."
        python3 -m uvicorn proxy:app --host 127.0.0.1 --port 8000 --workers 2 > /data/cache/fastapi_gateway.log 2>&1 &
        FASTAPI_PID=$!
    fi

    if [ -n "$NGINX_PID" ] && ! kill -0 $NGINX_PID 2>/dev/null; then
        echo "[CRITICAL] Nginx process died! Restarting..."
        nginx -g 'daemon off;' -c /nginx.conf &
        NGINX_PID=$!
    fi

    if [ -n "$OMNIROUTE_PID" ] && ! kill -0 $OMNIROUTE_PID 2>/dev/null; then
        echo "[CRITICAL] OmniRoute process died! Restarting..."
        (cd /omniroute && node server.js) > /data/omniroute/omniroute.log 2>&1 &
        OMNIROUTE_PID=$!
    fi

    if [ -n "$HERMES_PID" ] && [ -n "$HERMES_START_CMD" ] && ! kill -0 $HERMES_PID 2>/dev/null; then
        echo "[CRITICAL] Hermes Agent process died! Restarting..."
        $HERMES_START_CMD 2>&1 | tee /data/cache/hermes.log | sed 's/^/[HERMES] /' &
        HERMES_PID=$!
    fi

    sleep 5
done
