FROM debian:bookworm-slim

# /data is mounted as a persistent HF dataset bucket (Jishnupg/Opencode-Cli-storage)
# All opencode data (sessions, DB, config) goes here so it survives container restarts
ENV XDG_DATA_HOME=/data/share
ENV XDG_CONFIG_HOME=/data/config
ENV XDG_CACHE_HOME=/root/.cache
ENV XDG_STATE_HOME=/data/state

ARG OPENCODE_VERSION=1.18.3

# Install dependencies (git, python3, curl, ca-certificates, nginx, gnupg, lsb-release, and build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    nginx \
    gnupg \
    lsb-release \
    build-essential \
    make \
    g++ \
 && rm -rf /var/lib/apt/lists/*

# Add official Jellyfin APT repository & install Jellyfin server, web UI, and FFmpeg
RUN mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/jellyfin.gpg arch=amd64] https://repo.jellyfin.org/debian bookworm main" > /etc/apt/sources.list.d/jellyfin.list \
 && apt-get update && apt-get install -y --no-install-recommends jellyfin-server jellyfin-web ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Install aiohttp, pyrogram, tgcrypto, and Open WebUI
RUN pip3 install --no-cache-dir aiohttp pyrogram tgcrypto open-webui --break-system-packages || true

# Install Node.js 22.22.2 LTS (meets OmniRoute's minimum required runtime v22.22.2+)
RUN curl -fsSL https://nodejs.org/dist/v22.22.2/node-v22.22.2-linux-x64.tar.gz \
    | tar -xz -C /usr/local --strip-components=1

# Install OmniRoute globally, repair runtime binaries (better-sqlite3), and ensure Next.js cache dirs are writable
RUN npm install -g omniroute \
 && OMNIROUTE_PKG="$(npm root -g)/omniroute" \
 && omniroute runtime repair || true \
 && mkdir -p "${OMNIROUTE_PKG}/.next/cache" "${OMNIROUTE_PKG}/.build/next/cache" /root/.cache /data/cache /data/omniroute \
 && chmod -R 777 "${OMNIROUTE_PKG}" /root/.cache /data/cache /data/omniroute

# Download opencode binary
RUN curl -fsSL "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-x64.tar.gz" \
    | tar -xz -C /usr/local/bin opencode

# Working directory for projects
RUN mkdir -p /projects/default

COPY cleaner.py /cleaner.py
COPY entrypoint.sh /entrypoint.sh
COPY nginx.conf /nginx.conf
COPY proxy.py /proxy.py
COPY tg_streamer.py /tg_streamer.py
COPY gateway /gateway
COPY index.html /index.html
RUN chmod +x /entrypoint.sh

WORKDIR /projects/default

EXPOSE 4096

ENTRYPOINT ["/entrypoint.sh"]
