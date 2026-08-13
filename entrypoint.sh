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
mkdir -p /root/.cache /data/cache 2>/dev/null || true
chmod -R 777 /root/.cache /data/cache 2>/dev/null || true

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

# Step 8: Start OmniRoute AI Gateway in Background (if available)
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
    if [ -f "/data/open-webui/webui.db" ] && [ -s "/data/open-webui/webui.db" ]; then
        python3 -c "
import sqlite3, os
db = '/data/open-webui/webui.db'
try:
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='banner'\")
    if not cur.fetchone():
        conn.close()
        os.rename(db, db + '.legacy_bak')
        print('[RESET] Outdated Open WebUI DB backed up for clean schema init.')
    else:
        conn.close()
except Exception:
    pass
" 2>/dev/null || true
        if [ -f "/data/open-webui/webui.db" ]; then
            cp -f /data/open-webui/webui.db /root/.open-webui/webui.db 2>/dev/null || true
            echo "[PERSISTENCE] Restored Open WebUI database."
        fi
    fi

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

    export WEBUI_URL="http://127.0.0.1:8098"
    export OPENAI_API_BASE_URL="http://127.0.0.1:8000/v1"
    export OPENAI_API_KEY="omniroute"
    export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-opencode_webui_jwt_secret_2026}"
    export ENABLE_OLLAMA_API="false"
    export ENABLE_OPENAI_API="true"
    export TOOL_SERVERS=""
    export OPENAPI_TOOL_SERVERS=""
    export PORT=8098
    export DATA_DIR="/root/.open-webui"
    export CORS_ALLOW_ORIGIN="*"
    export WEBUI_AUTH="true"
    export ENABLE_SIGNUP="true"
    
    open-webui serve --port 8098 > /data/cache/openwebui.log 2>&1 &
    WEBUI_PID=$!
fi

# Start Periodic 120s Database Persistence Backup Daemon
(
    while true; do
        sleep 120
        sync_omniroute_db >/dev/null 2>&1 || true
        if [ -f "/root/.open-webui/webui.db" ]; then
            mkdir -p /data/open-webui 2>/dev/null || true
            cp -f /root/.open-webui/webui.db /data/open-webui/webui.db 2>/dev/null || true
        fi
    done
) &

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

    sleep 5
done
