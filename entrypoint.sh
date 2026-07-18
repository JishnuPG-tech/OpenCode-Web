#!/bin/sh

echo "=== OpenCode Space starting up ==="

# Configure Git to trust all directories to prevent ownership errors
git config --global --add safe.directory '*' 2>/dev/null || true

# /data is the persistent HF dataset bucket mount (Jishnupg/Opencode-Cli-storage)
# Try to create subdirectory structure - silently ignore failures if not writable yet
echo "Setting up /data directories..."
mkdir -p /data/share/opencode 2>/dev/null || true
mkdir -p /data/config/opencode 2>/dev/null || true
mkdir -p /data/cache/opencode 2>/dev/null || true
mkdir -p /data/state/opencode 2>/dev/null || true

# Always ensure /projects/default exists
mkdir -p /projects/default

# Start the SQLite self-healing daemon in the background
python3 /cleaner.py &

# Navigate to the default projects directory
cd /projects/default

# If GITHUB_REPO is not set, use the default OpenCode Drive repo
GITHUB_REPO="${GITHUB_REPO:-https://github.com/JishnuPG-tech/OpenCode-Drive.git}"

# Check current state
HAS_GIT=$(test -d ".git" && echo "yes" || echo "no")
HAS_REMOTE=$(git remote -v 2>/dev/null | grep -c origin || echo "0")
IS_EMPTY=$(test -z "$(ls -A . 2>/dev/null | grep -v '^\.')" && echo "yes" || echo "no")

echo "State: has_git=$HAS_GIT has_remote=$HAS_REMOTE is_empty=$IS_EMPTY"

if [ "$HAS_GIT" = "no" ] && [ "$IS_EMPTY" = "yes" ]; then
    echo "Empty directory. Cloning $GITHUB_REPO ..."
    git clone "$GITHUB_REPO" . 2>&1 || true
elif [ "$HAS_GIT" = "yes" ] && [ "$HAS_REMOTE" -gt "0" ]; then
    echo "Repo exists with remote. Pulling latest..."
    git pull origin HEAD 2>/dev/null || true
else
    echo "Using existing files in /projects/default."
fi

# Final safety: ensure a git repo exists (OpenCode requires one)
if [ ! -d .git ]; then
    echo "No .git found. Initializing bare repo..."
    git init
    git config user.email 'opencode@local.com'
    git config user.name 'OpenCode'
    git commit --allow-empty -m 'Initial commit'
fi

echo "=== Launching OpenCode server ==="
exec opencode serve --port 4096 --hostname 0.0.0.0
