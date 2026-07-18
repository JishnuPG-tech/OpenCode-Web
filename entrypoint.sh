#!/bin/sh
set -e

echo "=== OpenCode Space starting up ==="

# Configure Git to trust all directories to prevent ownership errors
git config --global --add safe.directory '*' || true

# /data is the persistent HF dataset bucket mount (Jishnupg/Opencode-Cli-storage)
# Create the expected subdirectory structure inside it
echo "Setting up persistent /data directories..."
mkdir -p /data/share/opencode
mkdir -p /data/config/opencode
mkdir -p /data/cache/opencode
mkdir -p /data/state/opencode
mkdir -p /projects/default

# Start the SQLite self-healing daemon in the background
python3 /cleaner.py &

# Navigate to the default projects directory
cd /projects/default

# If GITHUB_REPO is provided, try to clone it if the directory is empty
if [ -n "$GITHUB_REPO" ]; then
    echo "Found GITHUB_REPO: $GITHUB_REPO"
    if [ ! -d ".git" ] && [ -z "$(ls -A 2>/dev/null)" ]; then
        echo "Cloning repository..."
        git clone "$GITHUB_REPO" .
        echo "Clone successful!"
    else
        echo "Repo already present, skipping clone."
    fi
fi

# Ensure a git repo is initialized (OpenCode requires one)
if [ ! -d .git ]; then
    echo "Initializing empty git repository..."
    git init
    git config user.email 'opencode@local.com'
    git config user.name 'OpenCode'
    git commit --allow-empty -m 'Initial commit'
fi

echo "=== Launching OpenCode server ==="
exec opencode serve --port 4096 --hostname 0.0.0.0
