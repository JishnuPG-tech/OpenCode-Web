#!/bin/sh

echo "============================================"
echo "=== OpenCode Space starting up ==="
echo "Time: $(date)"
echo "============================================"

# Configure Git to trust all directories to prevent ownership errors
git config --global --add safe.directory '*' 2>/dev/null || true

# /data is the persistent HF dataset bucket mount
echo "[INIT] Setting up /data directories..."
mkdir -p /data/share/opencode 2>/dev/null || echo "[WARN] Could not create /data/share/opencode"
mkdir -p /data/config/opencode 2>/dev/null || echo "[WARN] Could not create /data/config/opencode"
mkdir -p /data/cache/opencode 2>/dev/null || echo "[WARN] Could not create /data/cache/opencode"
mkdir -p /data/state/opencode 2>/dev/null || echo "[WARN] Could not create /data/state/opencode"
mkdir -p /data/open-webui 2>/dev/null || echo "[WARN] Could not create /data/open-webui"
mkdir -p /data/omniroute 2>/dev/null || echo "[WARN] Could not create /data/omniroute"
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log /data/jellyfin/media/Movies /data/jellyfin/media/TVShows 2>/dev/null || true

# Symlink OmniRoute data directory to /data/omniroute for 100% persistence
if [ ! -L "/root/.omniroute" ]; then
    rm -rf /root/.omniroute 2>/dev/null || true
    ln -sf /data/omniroute /root/.omniroute
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
sleep 3

# Remove stale config that may have wrong model format
python3 -c "
import json, os
p = '/data/config/opencode/opencode.json'
stale_models = ['big-pickle', 'mimo-v2.5-free', 'opencode/mimo-v2.5-free']
try:
    d = json.load(open(p)) if os.path.exists(p) else {}
    if d.get('model') in stale_models:
        print(f'[CONFIG] Removing stale model {d[\"model\"]!r}, will regenerate')
        del d['model']
        json.dump(d, open(p, 'w'), indent=2)
except Exception as e:
    print(f'[CONFIG] Error normalizing: {e}')
" 2>/dev/null || true

# Start OmniRoute AI Gateway in background
echo "[INIT] Starting OmniRoute AI Gateway on port 20128..."
if command -v omniroute >/dev/null 2>&1; then
    omniroute serve --port 20128 --no-open &
    echo "[INIT] OmniRoute started in background."
else
    echo "[WARN] omniroute binary not found, skipping background service."
fi
sleep 2

# Pre-configure & Start Open WebUI on port 8098 (Mounted at WEBUI_PREFIX=/openwebui)
echo "[INIT] Starting Open WebUI on port 8098 pre-configured with OmniRoute..."
if command -v open-webui >/dev/null 2>&1; then
    export OPENAI_API_BASE_URL="http://127.0.0.1:20128/v1"
    export OPENAI_API_KEY="omniroute"
    export WEBUI_SECRET_KEY="opencode_webui_jwt_secret_2026"
    export ENABLE_OLLAMA_API="false"
    export ENABLE_OPENAI_API="true"
    export PORT=8098
    export DATA_DIR="/data/open-webui"
    export CORS_ALLOW_ORIGIN="*"
    export WEBUI_URL="https://jishnupg-opencode-cli.hf.space/openwebui"
    open-webui serve --port 8098 &
    echo "[INIT] Open WebUI started in background."
else
    echo "[WARN] open-webui binary not found, skipping."
fi

python3 -c "
import json, os
p = '/data/config/opencode/opencode.json'
try:
    d = json.load(open(p)) if os.path.exists(p) else {}
except Exception:
    d = {}
d['\$schema'] = 'https://opencode.ai/config.json'
d['server'] = {'port': 4097, 'hostname': '127.0.0.1'}
d['provider'] = d.get('provider', {})
d['provider']['omniroute'] = {
    'name': 'OmniRoute Gateway',
    'endpoint': 'http://127.0.0.1:20128/v1',
    'apiKey': 'omniroute'
}
if d.get('model') in [None, '', 'opencode/big-pickle', 'big-pickle', 'mimo-v2.5-free', 'opencode/mimo-v2.5-free']:
    d['model'] = 'omniroute/auto-best-coding'
json.dump(d, open(p, 'w'), indent=2)
print('[CONFIG] Wrote config with model:', d.get('model'))
" 2>/dev/null || true

echo "[DISK] /data usage:"
df -h /data 2>/dev/null || echo "[WARN] Could not check /data disk space"

# Check existing database
echo "[DB] Checking database..."
DB_PATH="/data/share/opencode/opencode.db"
if [ -f "$DB_PATH" ]; then
    echo "[DB] Found database at $DB_PATH ($(du -h "$DB_PATH" | cut -f1))"
else
    echo "[DB] No database found"
fi

# Remove stale SQLite WAL/lock files to prevent "database is locked" on startup
DB_PATH="/data/share/opencode/opencode.db"
if [ -f "${DB_PATH}-wal" ] || [ -f "${DB_PATH}-shm" ] || [ -f "${DB_PATH}.lock" ]; then
    echo "[DB] Removing stale SQLite lock/WAL files to prevent startup crash..."
    rm -f "${DB_PATH}-wal" "${DB_PATH}-shm" "${DB_PATH}.lock" 2>/dev/null || true
fi

# Start the SQLite self-healing daemon in the background
echo "[INIT] Starting self-healing daemon..."
python3 /cleaner.py &
sleep 1

# Always ensure /projects/default exists
mkdir -p /projects/default

# Navigate to the default projects directory
cd /projects/default

# If GITHUB_REPO is not set, use the default OpenCode Drive repo
GITHUB_REPO="${GITHUB_REPO:-https://github.com/JishnuPG-tech/OpenCode-Drive.git}"

# Check current state
HAS_GIT=$(test -d ".git" && echo "yes" || echo "no")
HAS_REMOTE=$(git remote -v 2>/dev/null | grep -c origin || echo "0")
IS_EMPTY=$(test -z "$(ls -A . 2>/dev/null | grep -v '^\.')" && echo "yes" || echo "no")

if [ "$HAS_GIT" = "no" ] && [ "$IS_EMPTY" = "yes" ]; then
    echo "[GIT] Empty directory. Cloning $GITHUB_REPO ..."
    git clone "$GITHUB_REPO" . 2>&1 || echo "[GIT] Clone FAILED"
elif [ "$HAS_GIT" = "yes" ] && [ "$HAS_REMOTE" -gt "0" ]; then
    echo "[GIT] Repo exists. Pulling latest..."
    git pull origin HEAD 2>/dev/null || echo "[GIT] Pull failed"
else
    echo "[GIT] Using existing files."
fi

# Final safety: ensure a git repo exists
if [ ! -d .git ]; then
    echo "[GIT] No .git found. Initializing..."
    git init
    git config user.email 'opencode@local.com'
    git config user.name 'OpenCode'
    git commit --allow-empty -m 'Initial commit'
fi

echo "============================================"
echo "=== Launching FastAPI Gateway Proxy on Port 4096 ==="
echo "============================================"

# Remove any stale DB lock files one final time before starting opencode
rm -f /data/share/opencode/opencode.db-wal \
       /data/share/opencode/opencode.db-shm \
       /data/share/opencode/opencode.db.lock 2>/dev/null || true

# Start OpenCode server with retry logic
_oc_start() {
    for attempt in 1 2 3; do
        echo "[OPENCODE] Start attempt $attempt..."
        opencode serve --port 4097 --hostname 127.0.0.1 &
        OC_PID=$!
        sleep 3
        if kill -0 $OC_PID 2>/dev/null; then
            echo "[OPENCODE] Server running (PID $OC_PID)"
            return 0
        fi
        echo "[OPENCODE] Attempt $attempt failed, waiting 2s before retry..."
        rm -f /data/share/opencode/opencode.db-wal \
               /data/share/opencode/opencode.db-shm \
               /data/share/opencode/opencode.db.lock 2>/dev/null || true
        sleep 2
    done
    echo "[OPENCODE] All start attempts failed"
}
_oc_start

cd /
exec python3 -m uvicorn proxy:app --host 0.0.0.0 --port 4096
