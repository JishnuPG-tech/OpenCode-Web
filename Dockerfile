FROM debian:bookworm-slim

# /data is mounted as a persistent HF dataset bucket (Jishnupg/Opencode-Cli-storage)
# All opencode data (sessions, DB, config) goes here so it survives container restarts
ENV XDG_DATA_HOME=/data/share
ENV XDG_CONFIG_HOME=/data/config
ENV XDG_CACHE_HOME=/data/cache
ENV XDG_STATE_HOME=/data/state

ARG OPENCODE_VERSION=1.18.3

# Install dependencies (including git, python3, curl, ca-certificates, nginx, and build tools for native modules)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    nginx \
    build-essential \
    make \
    g++ \
 && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 LTS (required for OmniRoute & undici dependencies)
RUN curl -fsSL https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-x64.tar.gz \
    | tar -xz -C /usr/local --strip-components=1

# Install OmniRoute globally
RUN npm install -g omniroute


# Download opencode binary
RUN curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-x64.tar.gz" \
    | tar -xz -C /usr/local/bin opencode

# Working directory for projects
RUN mkdir -p /projects/default

COPY cleaner.py /cleaner.py
COPY entrypoint.sh /entrypoint.sh
COPY nginx.conf /nginx.conf
RUN chmod +x /entrypoint.sh


WORKDIR /projects/default

EXPOSE 4096

ENTRYPOINT ["/entrypoint.sh"]
