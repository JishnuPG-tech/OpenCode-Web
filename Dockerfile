# ==============================================================================
# STAGE 1: Dedicated OmniRoute Production Builder (Node 24 Engine)
# ==============================================================================
FROM node:24-bookworm-slim AS omniroute-builder

WORKDIR /omniroute

ENV NEXT_TELEMETRY_DISABLED=1
ENV OMNIROUTE_USE_TURBOPACK=0
ENV NODE_OPTIONS="--max-old-space-size=4096"
ENV DISABLE_ESLINT_PLUGIN=true
ENV OMNIROUTE_BASE_PATH="/omniroute"
ENV NEXT_PUBLIC_OMNIROUTE_BASE_PATH="/omniroute"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git python3 build-essential make g++ sqlite3 libsqlite3-dev \
 && rm -rf /var/lib/apt/lists/*

COPY fix_omniroute.py /fix_omniroute.py

# Clone OmniRoute, repair migration collisions, install dependencies, rebuild better-sqlite3, and run production build STRICTLY WITHOUT || true
RUN git clone --depth 1 https://github.com/diegosouzapw/OmniRoute.git /omniroute \
 && python3 /fix_omniroute.py /omniroute \
 && npm install --legacy-peer-deps --no-audit --no-fund \
 && npm rebuild better-sqlite3 --build-from-source \
 && OMNIROUTE_BASE_PATH="/omniroute" NEXT_PUBLIC_OMNIROUTE_BASE_PATH="/omniroute" NEXT_TELEMETRY_DISABLED=1 OMNIROUTE_USE_TURBOPACK=0 NODE_OPTIONS="--max-old-space-size=4096" npm run build

# ==============================================================================
# STAGE 2: Multi-Service Production Runtime (Debian Bookworm)
# ==============================================================================
FROM debian:bookworm-slim

ENV XDG_DATA_HOME=/data/share
ENV XDG_CONFIG_HOME=/data/config
ENV XDG_CACHE_HOME=/root/.cache
ENV XDG_STATE_HOME=/data/state
ENV HOME=/root

# 1. Install System Dependencies, Python, C++ toolchain & Redis
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
    redis-server \
 && rm -rf /var/lib/apt/lists/*

# 2. Add Official Jellyfin APT Repository & Install Jellyfin Server, Web UI, and FFmpeg
RUN mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/jellyfin.gpg arch=amd64] https://repo.jellyfin.org/debian bookworm main" > /etc/apt/sources.list.d/jellyfin.list \
 && apt-get update && apt-get install -y --no-install-recommends jellyfin-server jellyfin-web ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# 3. Install Python AI Stack (CPU PyTorch + Open WebUI + Sentence Transformers)
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu --break-system-packages \
 && pip3 install --no-cache-dir aiohttp pyrogram tgcrypto open-webui httpx uvicorn fastapi sentence-transformers --break-system-packages || true

# Pre-cache Open WebUI default embedding model inside Docker image for 1s startup
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" || true

# 4. Install Node.js 24 LTS Runtime into final container
RUN curl -fsSL https://nodejs.org/dist/v24.1.0/node-v24.1.0-linux-x64.tar.gz 2>/dev/null \
    || curl -fsSL https://nodejs.org/dist/v22.22.2/node-v22.22.2-linux-x64.tar.gz \
    | tar -xz -C /usr/local --strip-components=1

# 5. Copy pre-compiled OmniRoute production runtime from Stage 1
COPY --from=omniroute-builder /omniroute /omniroute

RUN mkdir -p /root/.cache /data/cache /data/omniroute /data/open-webui
RUN chmod -R 777 /root/.cache /data/cache /omniroute

# 6. Copy Gateway Proxy Application & Entrypoint Scripts
WORKDIR /
COPY fix_omniroute.py /fix_omniroute.py
COPY entrypoint.sh /entrypoint.sh
COPY nginx.conf /nginx.conf
COPY proxy.py /proxy.py
COPY tg_streamer.py /tg_streamer.py
COPY gateway /gateway
COPY index.html /index.html
RUN chmod +x /entrypoint.sh

EXPOSE 4096

ENTRYPOINT ["/entrypoint.sh"]
