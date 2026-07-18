#!/bin/sh
set -e

echo "Starting OpenCode Space entrypoint..."

# Configure Git to trust all directories inside the container to prevent ownership errors
git config --global --add safe.directory '*' || true

# Ensure the opencode data directories exist inside /projects (which is persistent)
mkdir -p /projects/.opencode/share
mkdir -p /projects/.opencode/config
mkdir -p /projects/.opencode/cache
mkdir -p /projects/.opencode/state
mkdir -p /projects/default

# Start the SQLite self-healing database daemon in the background
python3 /cleaner.py &

# Navigate to the default projects directory
cd /projects/default

# If GITHUB_REPO is provided, try to clone it if the directory is empty
if [ -n "$GITHUB_REPO" ]; then
    echo "Found GITHUB_REPO environment variable: $GITHUB_REPO"
    
    # Check if the directory is empty (ignoring hidden files except .git)
    if [ ! -d ".git" ] && [ -z "$(ls -A 2>/dev/null)" ]; then
        echo "Directory is empty. Cloning repository..."
        git clone "$GITHUB_REPO" .
        echo "Clone successful!"
    else
        echo "Directory is not empty or already has a git repo. Skipping clone."
    fi
fi

# Ensure a git repo is initialized (OpenCode requires one to serve properly)
if [ ! -d .git ]; then
    echo "No git repository found. Initializing empty repository..."
    git init
    git config user.email 'opencode@local.com'
    git config user.name 'OpenCode'
    git commit --allow-empty -m 'Initial commit'
fi

echo "Launching OpenCode server..."
exec opencode serve --port 4096 --hostname 0.0.0.0
