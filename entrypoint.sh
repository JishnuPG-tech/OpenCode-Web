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
mkdir -p /data/jellyfin/data /data/jellyfin/config /data/jellyfin/cache /data/jellyfin/log 2>/dev/null || true

# Start Telegram Direct Range Stream Proxy in background
echo "[INIT] Starting Telegram Direct Stream Proxy on port 8080..."
python3 /tg_streamer.py &

# Start Jellyfin Media Server in background
echo "[INIT] Starting Jellyfin Media Server on port 8096..."
export JELLYFIN_DATA_DIR=/data/jellyfin/data
export JELLYFIN_CONFIG_DIR=/data/jellyfin/config
export JELLYFIN_CACHE_DIR=/data/jellyfin/cache
export JELLYFIN_LOG_DIR=/data/jellyfin/log

if command -v jellyfin >/dev/null 2>&1; then
    jellyfin --http-port 8096 &
elif command -v jellyfin-server >/dev/null 2>&1; then
    jellyfin-server --http-port 8096 &
elif [ -f "/usr/bin/jellyfin" ]; then
    /usr/bin/jellyfin --http-port 8096 &
else
    echo "[WARN] Could not find jellyfin binary"
fi
sleep 2


# Ensure config exists with correct model setting
echo "[CONFIG] Setting up default configuration..."


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
echo "[CONFIG] Current configuration:"
cat /data/config/opencode/opencode.json 2>/dev/null || echo "{}"


# Log disk space
echo "[DISK] /data usage:"
df -h /data 2>/dev/null || echo "[WARN] Could not check /data disk space"

# Check existing database
echo "[DB] Checking database..."
DB_PATH="/data/share/opencode/opencode.db"
if [ -f "$DB_PATH" ]; then
    echo "[DB] Found database at $DB_PATH ($(du -h "$DB_PATH" | cut -f1))"
    # Count sessions
    python3 -c "
import sqlite3
try:
    conn = sqlite3.connect('$DB_PATH', timeout=5)
    c = conn.cursor()
    # List all tables
    c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
    tables = [r[0] for r in c.fetchall()]
    print(f'[DB] Tables: {tables}')
    if 'session' in tables:
        c.execute('PRAGMA table_info(session)')
        cols = [r[1] for r in c.fetchall()]
        print(f'[DB] Session columns: {cols}')
        c.execute('SELECT COUNT(*) FROM session')
        count = c.fetchone()[0]
        print(f'[DB] Total sessions: {count}')
        c.execute('SELECT id, title, directory FROM session LIMIT 5')
        for row in c.fetchall():
            print(f'[DB]   Session: {row[0]} title={row[1]!r} dir={row[2]!r}')
    conn.close()
except Exception as e:
    print(f'[DB] Error: {e}')
" 2>/dev/null || echo "[DB] Could not read database"
else
    echo "[DB] No database found"
fi

# Start the SQLite self-healing daemon in the background
echo "[INIT] Starting self-healing daemon..."
python3 /cleaner.py &

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

echo "[GIT] State: has_git=$HAS_GIT has_remote=$HAS_REMOTE is_empty=$IS_EMPTY"

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

echo "[GIT] Files: $(ls -1 . 2>/dev/null | grep -v '^\.git$' | tr '\n' ', ')"

# Log key env vars
echo "[ENV] API keys: ANTHROPIC=$(if [ -n \"$ANTHROPIC_API_KEY\" ]; then echo SET; else echo NOT_SET; fi) OPENAI=$(if [ -n \"$OPENAI_API_KEY\" ]; then echo SET; else echo NOT_SET; fi)"
echo "[ENV] Auth: USER=$(if [ -n \"$OPENCODE_SERVER_USERNAME\" ]; then echo SET; else echo NOT_SET; fi) PASS=$(if [ -n \"$OPENCODE_SERVER_PASSWORD\" ]; then echo SET; else echo NOT_SET; fi)"

# Test connectivity to OpenCode Zen API
echo "[NET] Testing connectivity to opencode.ai/zen..."
ZEN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "https://opencode.ai/zen/v1/models" 2>/dev/null || echo "000")
echo "[NET] OpenCode Zen API status: $ZEN_STATUS"

if [ "$ZEN_STATUS" = "200" ]; then
    echo "[NET] OpenCode Zen API is reachable"
else
    echo "[NET] WARNING: OpenCode Zen API may not be reachable from this container"
    echo "[NET] This means free models may not work - AI responses will fail silently"
fi

echo "============================================"
echo "=== Launching OpenCode server & Nginx Proxy ==="
echo "============================================"
opencode serve --port 4097 --hostname 127.0.0.1 &
sleep 2
exec nginx -g "daemon off;" -c /nginx.conf

