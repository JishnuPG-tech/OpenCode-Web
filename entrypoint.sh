#!/bin/sh

echo "============================================"
echo "=== OpenCode Space starting up ==="
echo "Time: $(date)"
echo "============================================"

# Configure Git to trust all directories to prevent ownership errors
git config --global --add safe.directory '*' 2>/dev/null || true

# /data is the persistent HF dataset bucket mount (Jishnupg/Opencode-Cli-storage)
echo "[INIT] Setting up /data directories..."
mkdir -p /data/share/opencode 2>/dev/null || echo "[WARN] Could not create /data/share/opencode"
mkdir -p /data/config/opencode 2>/dev/null || echo "[WARN] Could not create /data/config/opencode"
mkdir -p /data/cache/opencode 2>/dev/null || echo "[WARN] Could not create /data/cache/opencode"
mkdir -p /data/state/opencode 2>/dev/null || echo "[WARN] Could not create /data/state/opencode"

# Log XDG paths
echo "[ENV] XDG_DATA_HOME=$XDG_DATA_HOME"
echo "[ENV] XDG_CONFIG_HOME=$XDG_CONFIG_HOME"
echo "[ENV] XDG_CACHE_HOME=$XDG_CACHE_HOME"
echo "[ENV] XDG_STATE_HOME=$XDG_STATE_HOME"

# Log disk space
echo "[DISK] /data usage:"
df -h /data 2>/dev/null || echo "[WARN] Could not check /data disk space"
echo "[DISK] /projects usage:"
df -h /projects 2>/dev/null || echo "[WARN] Could not check /projects disk space"

# Check existing config
echo "[CONFIG] Checking opencode config..."
if [ -f /data/config/opencode/opencode.json ]; then
    echo "[CONFIG] Found config at /data/config/opencode/opencode.json:"
    cat /data/config/opencode/opencode.json
else
    echo "[CONFIG] No config found at /data/config/opencode/opencode.json"
fi

# Check existing database
echo "[DB] Checking database..."
DB_PATH="/data/share/opencode/opencode.db"
if [ -f "$DB_PATH" ]; then
    echo "[DB] Found database at $DB_PATH"
    ls -la "$DB_PATH"
    # Count sessions
    python3 -c "
import sqlite3
try:
    conn = sqlite3.connect('$DB_PATH', timeout=5)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM session')
    count = c.fetchone()[0]
    print(f'[DB] Total sessions: {count}')
    c.execute('SELECT id, status, directory FROM session LIMIT 10')
    for row in c.fetchall():
        print(f'[DB]   Session: {row[0]} status={row[1]} dir={row[2]}')
    conn.close()
except Exception as e:
    print(f'[DB] Error reading database: {e}')
" 2>/dev/null || echo "[DB] Could not read database"
else
    echo "[DB] No database found at $DB_PATH"
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
echo "[GIT] Working directory: $(pwd)"
echo "[GIT] Files in directory:"
ls -la . 2>/dev/null || echo "[GIT] Could not list directory"

if [ "$HAS_GIT" = "no" ] && [ "$IS_EMPTY" = "yes" ]; then
    echo "[GIT] Empty directory. Cloning $GITHUB_REPO ..."
    git clone "$GITHUB_REPO" . 2>&1 || echo "[GIT] Clone failed!"
    echo "[GIT] After clone, files:"
    ls -la . 2>/dev/null
elif [ "$HAS_GIT" = "yes" ] && [ "$HAS_REMOTE" -gt "0" ]; then
    echo "[GIT] Repo exists with remote. Pulling latest..."
    git pull origin HEAD 2>/dev/null || echo "[GIT] Pull failed"
else
    echo "[GIT] Using existing files in /projects/default."
fi

# Final safety: ensure a git repo exists (OpenCode requires one)
if [ ! -d .git ]; then
    echo "[GIT] No .git found. Initializing bare repo..."
    git init
    git config user.email 'opencode@local.com'
    git config user.name 'OpenCode'
    git commit --allow-empty -m 'Initial commit'
fi

echo "[GIT] Final git status:"
git status 2>/dev/null || echo "[GIT] Not a git repo"
echo "[GIT] Remote:"
git remote -v 2>/dev/null || echo "[GIT] No remote"

# Log environment variables (redact secrets)
echo "[ENV] Environment:"
echo "[ENV]   HOME=$HOME"
echo "[ENV]   USER=$(whoami)"
echo "[ENV]   PWD=$(pwd)"
echo "[ENV]   ANTHROPIC_API_KEY=$(if [ -n \"$ANTHROPIC_API_KEY\" ]; then echo 'SET'; else echo 'NOT SET'; fi)"
echo "[ENV]   OPENAI_API_KEY=$(if [ -n \"$OPENAI_API_KEY\" ]; then echo 'SET'; else echo 'NOT SET'; fi)"
echo "[ENV]   OPENCODE_SERVER_USERNAME=$(if [ -n \"$OPENCODE_SERVER_USERNAME\" ]; then echo 'SET'; else echo 'NOT SET'; fi)"
echo "[ENV]   OPENCODE_SERVER_PASSWORD=$(if [ -n \"$OPENCODE_SERVER_PASSWORD\" ]; then echo 'SET'; else echo 'NOT SET'; fi)"
echo "[ENV]   GITHUB_REPO=$GITHUB_REPO"

echo "============================================"
echo "=== Launching OpenCode server ==="
echo "============================================"
exec opencode serve --port 4096 --hostname 0.0.0.0
