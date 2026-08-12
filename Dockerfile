FROM debian:bookworm-slim

# Persistent data environment setup for Hugging Face Spaces (/data bucket mount)
ENV XDG_DATA_HOME=/data/share
ENV XDG_CONFIG_HOME=/data/config
ENV XDG_CACHE_HOME=/root/.cache
ENV XDG_STATE_HOME=/data/state
ENV HOME=/root

ARG OMNIROUTE_VERSION=main

# 1. Install System Dependencies & C++ Build Toolchain (for better-sqlite3 native bindings)
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
    sqlite3 \
    libsqlite3-dev \
 && rm -rf /var/lib/apt/lists/*

# 2. Add Official Jellyfin APT Repository & Install Jellyfin Server, Web UI, and FFmpeg
RUN mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/jellyfin.gpg arch=amd64] https://repo.jellyfin.org/debian bookworm main" > /etc/apt/sources.list.d/jellyfin.list \
 && apt-get update && apt-get install -y --no-install-recommends jellyfin-server jellyfin-web ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# 3. Install Python Dependencies (CPU PyTorch to avoid massive CUDA wheels, plus Open WebUI & utilities)
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu --break-system-packages \
 && pip3 install --no-cache-dir aiohttp pyrogram tgcrypto open-webui httpx uvicorn fastapi --break-system-packages || true

# 4. Install Node.js 22.22.2 LTS (meets OmniRoute's minimum required runtime v22.22.2+)
RUN curl -fsSL https://nodejs.org/dist/v22.22.2/node-v22.22.2-linux-x64.tar.gz \
    | tar -xz -C /usr/local --strip-components=1

# 5. Clone and Build OmniRoute AI Gateway
WORKDIR /omniroute
ENV NEXT_TELEMETRY_DISABLED=1
ENV OMNIROUTE_USE_TURBOPACK=0
ENV NODE_OPTIONS="--max-old-space-size=2048"
ENV DISABLE_ESLINT_PLUGIN=true

RUN git clone --depth 1 https://github.com/diegosouzapw/OmniRoute.git /omniroute \
 && npm install --legacy-peer-deps \
 && npm rebuild better-sqlite3 --build-from-source \
 && NEXT_TELEMETRY_DISABLED=1 OMNIROUTE_USE_TURBOPACK=0 NODE_OPTIONS="--max-old-space-size=2048" npm run build || true

RUN mkdir -p /root/.cache /data/cache /data/omniroute /data/open-webui
RUN chmod -R 777 /root/.cache /data/cache /omniroute

# 6. Copy Gateway Proxy Application & Entrypoint Scripts
WORKDIR /
COPY entrypoint.sh /entrypoint.sh
COPY nginx.conf /nginx.conf
COPY proxy.py /proxy.py
COPY tg_streamer.py /tg_streamer.py
COPY gateway /gateway
COPY index.html /index.html
RUN chmod +x /entrypoint.sh

EXPOSE 4096

ENTRYPOINT ["/entrypoint.sh"]
