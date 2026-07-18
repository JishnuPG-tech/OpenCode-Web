#!/bin/sh
set -e

echo "=== OpenCode Space starting up ==="

# Configure Git to trust all directories to prevent ownership errors
git config --global --add safe.directory '*' || true

# /data is the persistent HF dataset bucket mount (Jishnupg/Opencode-Cli-storage)
# Create the expected subdirectory structure inside it
# NOTE: /data may not be writable immediately - handle gracefully
echo "Setting up persistent /data directories..."
mkdir -p /data/share/opencode 2>/dev/null || true
mkdir -p /data/config/opencode 2>/dev/null || true
mkdir -p /data/cache/opencode 2>/dev/null || true
mkdir -p /data/state/opencode 2>/dev/null || true
mkdir -p /projects/default

# Start the SQLite self-healing daemon in the background
python3 /cleaner.py &

# Navigate to the default projects directory
cd /projects/default

# If GITHUB_REPO is not set, use the default OpenCode Drive repo
GITHUB_REPO="${GITHUB_REPO:-https://github.com/JishnuPG-tech/OpenCode-Drive.git}"

# Clone the repo if the directory is empty (no .git)
if [ ! -d ".git" ] && [ -z "$(ls -A 2>/dev/null | grep -v '^\.')" ]; then
    echo "Cloning repository: $GITHUB_REPO ..."
    git clone "$GITHUB_REPO" . 2>&1 || true
    echo "Clone step done."
elif [ -d ".git" ] && git remote -v 2>/dev/null | grep -q origin; then
    echo "Repo already cloned, pulling latest..."
    git pull origin HEAD 2>/dev/null || true
else
    echo "Directory has existing content. Using as-is."
fi

# Ensure a git repo exists (OpenCode requires one to serve properly)
if [ ! -d .git ]; then
    echo "Initializing empty git repository..."
    git init
    git config user.email 'opencode@local.com'
    git config user.name 'OpenCode'
    git commit --allow-empty -m 'Initial commit'
fi

echo "=== Launching OpenCode server ==="
exec opencode serve --port 4096 --hostname 0.0.0.0
