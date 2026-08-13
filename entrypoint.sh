#!/bin/sh

echo "============================================"
echo "=== OpenCode Space starting up ==="
echo "Time: $(date)"
echo "============================================"

git config --global --add safe.directory '*' 2>/dev/null || true

# ── Master Secret Validation (Must be provided via HF Space Secrets) ─────────
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

export ENCRYPTION_SECRET="${STORAGE_ENCRYPTION_KEY}"
export OMNIROUTE_SECRET_KEY="${STORAGE_ENCRYPTION_KEY}"
export OMNIROUTE_WS_BRIDGE_SECRET="${OMNIROUTE_WS_BRIDGE_SECRET:-$(echo "ws_bridge_${JWT_SECRET}" | sha256sum | cut -c1-48)}"
export WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-$(echo "owui_${JWT_SECRET}" | sha256sum | cut -c1-56)}"

# Purge any legacy secret env files from storage bucket to maintain strict secret separation
rm -f /data/.env /data/secrets.env /data/secrets /data/config/.env /data/omniroute/.env /data/omniroute/secrets.env /data/omniroute/secrets /data/omniroute/.secrets /data/omniroute/server.env 2>/dev/null || true

# Display configured secret status (without logging sensitive raw token values)
echo "[INIT] STORAGE_ENCRYPTION_KEY is configured"
echo "[INIT] JWT_SECRET is configured"
echo "[INIT] API_KEY_SECRET is configured"

# ── Deterministic Paths & Directory Model ────────────────────────────────────
PERSIST_DIR="/data/omniroute"
PERSIST_DB="/data/omniroute/storage.sqlite"
BACKUP_DIR="/data/omniroute/backups"

RUNTIME_DIR="/root/.omniroute"
RUNTIME_DB="/root/.omniroute/storage.sqlite"

# Clean up legacy directory collision if storage.sqlite was created as a folder
if [ -d "$PERSIST_DB" ]; then
    echo "[PERSISTENCE] Fixing directory collision: removing directory $PERSIST_DB..."
    rm -rf "$PERSIST_DB"
fi

mkdir -p "$PERSIST_DIR" "$BACKUP_DIR" "$RUNTIME_DIR" 2>/dev/null || true

echo "[PERSISTENCE] Storage mount inspection:"
mount | grep -E 'hf|bucket|data|fuse|nfs' || echo "[STORAGE] /data info: $(df -h /data 2>&1 || true)"

# ── Snapshot & State Restoration on Boot ──────────────────────────────────────
if [ -f "$PERSIST_DB" ] && [ -s "$PERSIST_DB" ]; then
    _INIT_SIZE=$(wc -c < "$PERSIST_DB" 2>/dev/null | tr -d ' \t\n\r' || echo "0")
    echo "[PERSISTENCE] Found OmniRoute snapshot at: ${PERSIST_DB} (${_INIT_SIZE} bytes)"
    if command -v sqlite3 >/dev/null 2>&1; then
        _CHK=$(sqlite3 "$PERSIST_DB" "PRAGMA quick_check;" 2>/dev/null || echo "failed")
        echo "[PERSISTENCE] Snapshot integrity check: ${_CHK}"
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
else
    echo "[PERSISTENCE] No snapshot found at ${PERSIST_DB}. Initializing fresh OmniRoute database."
fi

# ── One-time targeted cleanup: remove credential rows that fail to decrypt ────
# These two specific rows were encrypted under a STORAGE_ENCRYPTION_KEY that no
# longer matches the active one and are permanently unreadable. Rather than wipe
# the whole DB, delete only these rows so the user can re-add the connection.
# Safe to leave in permanently: this is a no-op once the rows are gone.
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
                        print(f"[CLEANUP] Deleted {cur.rowcount} row(s) from {table}.{col} matching {prefix[:20]}...")
                        deleted_total += cur.rowcount
                except sqlite3.OperationalError:
                    pass
    conn.commit()
    conn.close()
    if deleted_total:
        print(f"[CLEANUP] Removed {deleted_total} unrecoverable credential row(s) total.")
    else:
        print("[CLEANUP] No matching broken credential rows found (already clean).")
except Exception as e:
    print(f"[CLEANUP] Skipped due to error: {e}")
PYEOF
fi

# Restore supplementary state directories (oauth, credentials, runtime, gemini_cli, config_dir)
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
        echo "[PERSISTENCE] Restored persistent state directory: ${_ITEM}"
    fi
done

# ── Unified Single Backup Pipeline ───────────────────────────────────────────
sync_omniroute_db() {
    if [ -f "$RUNTIME_DB" ] && [ -s "$RUNTIME_DB" ]; then
        mkdir -p "$PERSIST_DIR" "$BACKUP_DIR" 2>/dev/null || true
        
        # 1. SQLite WAL-aware database backup
        if command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 "$RUNTIME_DB" ".backup '$PERSIST_DB'" 2>/dev/null || cp -f "$RUNTIME_DB" "$PERSIST_DB" 2>/dev/null || true
        else
            cp -f "$RUNTIME_DB" "$PERSIST_DB" 2>/dev/null || true
        fi

        # 2. Verify persistent snapshot integrity
        _CHK="ok"
        if command -v sqlite3 >/dev/null 2>&1; then
            _CHK=$(sqlite3 "$PERSIST_DB" "PRAGMA quick_check;" 2>/dev/null || echo "failed")
        fi

        if [ "$_CHK" = "ok" ]; then
            # Rotate database backups (keep last-known-good + 5 rolling snapshots)
            cp -f "$PERSIST_DB" "${BACKUP_DIR}/last-known-good.sqlite" 2>/dev/null || true
            TIMESTAMP=$(date +%Y%m%d-%H%M)
            cp -f "$PERSIST_DB" "${BACKUP_DIR}/storage-${TIMESTAMP}.sqlite" 2>/dev/null || true
            ls -t "${BACKUP_DIR}"/storage-*.sqlite 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true
            
            # 3. Synchronize supplementary state directories
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
        else
            echo "[PERSISTENCE] WARNING: Backup snapshot integrity check failed."
        fi
    fi
}

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

# Official OmniRoute Public Base URL & Production HTTPS Settings
export NEXT_PUBLIC_BASE_URL="https://jishnupg-opencode-cli.hf.space"
export AUTH_COOKIE_SECURE="true"
export ALLOW_REMOTE_OAUTH="true"
export ALLOW_BROWSER_OAUTH="true"

# Explicit Public OAuth Callback URLs
export OAUTH_CALLBACK_URL="https://jishnupg-opencode-cli.hf.space/callback"
export NEXT_PUBLIC_OAUTH_CALLBACK_URL="https://jishnupg-opencode-cli.hf.space/callback"
export REDIRECT_URI="https://jishnupg-opencode-cli.hf.space/callback"
export ANTIGRAVITY_OAUTH_REDIRECT_URI="https://jishnupg-opencode-cli.hf.space/callback"
export ANTIGRAVITY_REDIRECT_URI="https://jishnupg-opencode-cli.hf.space/callback"

# Admin credentials for OmniRoute (loaded directly from HF Space Secret INITIAL_PASSWORD)
if [ -z "$INITIAL_PASSWORD" ]; then
    echo "[FATAL ERROR] INITIAL_PASSWORD is not set in Hugging Face Space Secrets!"
    echo "[FATAL ERROR] INITIAL_PASSWORD is mandatory for OmniRoute authentication."
    exit 1
fi

export ADMIN_PASSWORD="$INITIAL_PASSWORD"
export OMNIROUTE_INITIAL_PASSWORD="$INITIAL_PASSWORD"
export OMNIROUTE_PASSWORD="$INITIAL_PASSWORD"
export PASSWORD="$INITIAL_PASSWORD"
export RESET_PASSWORD="$INITIAL_PASSWORD"
export OMNIROUTE_RESET_PASSWORD="$INITIAL_PASSWORD"

echo "[INIT] INITIAL_PASSWORD is configured"

if [ -f "$RUNTIME_DB" ] && [ -s "$RUNTIME_DB" ]; then
    echo "[AUTH] Existing admin credential record: present in runtime database"
else
    echo "[AUTH] Existing admin credential record: absent (fresh baseline initialization)"
fi

# CLI Fingerprint & Provider Compatibility Flags
export CLI_COMPAT_ANTIGRAVITY=1
export CLI_COMPAT_GITHUB=1
export CLI_COMPAT_KIMI_CODING=1
export CLI_COMPAT_CLAUDE=1
export CLI_COMPAT_CODEX=1
export CLI_COMPAT_CURSOR=1
export CLI_COMPAT_QWEN=1

# Optional Provider OAuth Client Credentials (loaded from Space Secrets if provided)
export ANTIGRAVITY_OAUTH_CLIENT_ID="${ANTIGRAVITY_OAUTH_CLIENT_ID:-}"
export ANTIGRAVITY_OAUTH_CLIENT_SECRET="${ANTIGRAVITY_OAUTH_CLIENT_SECRET:-}"
export GEMINI_CLI_OAUTH_CLIENT_ID="${GEMINI_CLI_OAUTH_CLIENT_ID:-}"
export GEMINI_CLI_OAUTH_CLIENT_SECRET="${GEMINI_CLI_OAUTH_CLIENT_SECRET:-}"
export GITHUB_OAUTH_CLIENT_ID="${GITHUB_OAUTH_CLIENT_ID:-}"
export KIMI_CODING_OAUTH_CLIENT_ID="${KIMI_CODING_OAUTH_CLIENT_ID:-}"

# Required secrets — crash early with a clear message if missing
export JWT_SECRET="${JWT_SECRET:?JWT_SECRET is not set. Add it to Hugging Face Space Secrets.}"
export API_KEY_SECRET="${API_KEY_SECRET:?API_KEY_SECRET is not set. Add it to Hugging Face Space Secrets.}"

# Optional secrets — auto-generate from JWT_SECRET if not explicitly set
# OMNIROUTE_WS_BRIDGE_SECRET: used only for the Live WebSocket monitoring bridge (port 20132)
if [ -z "$OMNIROUTE_WS_BRIDGE_SECRET" ]; then
    OMNIROUTE_WS_BRIDGE_SECRET="ws_bridge_$(echo "$JWT_SECRET" | sha256sum | cut -c1-48 2>/dev/null || echo "$JWT_SECRET" | md5sum | cut -c1-32)"
fi
export OMNIROUTE_WS_BRIDGE_SECRET

# WEBUI_SECRET_KEY: Open WebUI JWT signing secret (must be ≥32 chars)
if [ -z "$WEBUI_SECRET_KEY" ]; then
    WEBUI_SECRET_KEY="owui_$(echo "${JWT_SECRET}openwebui" | sha256sum | cut -c1-56 2>/dev/null || echo "${JWT_SECRET}openwebui" | md5sum | cut -c1-32)"
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
    # Disable local PyTorch/SentenceTransformers embedding engine to make Open WebUI lightweight & instant
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
    echo "[INIT] Open WebUI started in background (PID=${OWUI_PID}). Waiting for health..."
    OWUI_HEALTHY=0
    for i in $(seq 1 5); do
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
        echo "[INIT] Open WebUI continuing startup in background. Proceeding to launch Gateway and Nginx..."
    fi
else
    echo "[WARN] open-webui binary not found, skipping."
fi

echo "[DISK] /data usage:"
df -h /data 2>/dev/null || echo "[WARN] Could not check /data disk space"

echo "============================================"
echo "=== Launching FastAPI Gateway Proxy on Internal Port 8000 ==="
echo "============================================"

cd /
python3 -m uvicorn proxy:app --host 127.0.0.1 --port 8000 &
GATEWAY_PID=$!

echo "[INIT] FastAPI Gateway started in background (PID=${GATEWAY_PID}). Waiting for health..."
for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:8000/health/live" >/dev/null 2>&1; then
        echo "[HEALTH] FastAPI Gateway healthy on internal port 8000 after ${i}s"
        break
    fi
    if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
        echo "[ERROR] FastAPI Gateway process (PID=${GATEWAY_PID}) exited prematurely"
        break
    fi
    sleep 1
done

echo "============================================"
echo "=== Launching NGINX Edge Proxy on Public Port 4096 ==="
echo "============================================"

if command -v nginx >/dev/null 2>&1; then
    nginx -t 2>&1 || echo "[WARN] NGINX configuration test warning"
    nginx -g 'daemon off;' &
    NGINX_PID=$!
    echo "[INIT] NGINX started in background (PID=${NGINX_PID}). Waiting for health on port 4096..."
    for i in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:4096/health/live" >/dev/null 2>&1; then
            echo "[HEALTH] NGINX edge proxy healthy on public port 4096 after ${i}s"
            break
        fi
        if ! kill -0 "$NGINX_PID" 2>/dev/null; then
            echo "[ERROR] NGINX process (PID=${NGINX_PID}) exited prematurely"
            break
        fi
        sleep 1
    done
    wait "$NGINX_PID"
elif [ -f "/usr/sbin/nginx" ]; then
    /usr/sbin/nginx -t 2>&1 || echo "[WARN] NGINX configuration test warning"
    /usr/sbin/nginx -g 'daemon off;' &
    NGINX_PID=$!
    echo "[INIT] NGINX started in background (PID=${NGINX_PID}). Waiting for health on port 4096..."
    for i in $(seq 1 30); do
        if curl -fsS "http://127.0.0.1:4096/health/live" >/dev/null 2>&1; then
            echo "[HEALTH] NGINX edge proxy healthy on public port 4096 after ${i}s"
            break
        fi
        if ! kill -0 "$NGINX_PID" 2>/dev/null; then
            echo "[ERROR] NGINX process (PID=${NGINX_PID}) exited prematurely"
            break
        fi
        sleep 1
    done
    wait "$NGINX_PID"
else
    echo "[WARN] NGINX binary not found. Binding FastAPI Gateway directly to public port 4096 as fallback..."
    kill "$GATEWAY_PID" 2>/dev/null || true
    exec python3 -m uvicorn proxy:app --host 0.0.0.0 --port 4096
fi
