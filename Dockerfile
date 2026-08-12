# ==============================================================================
# STAGE 1: Dedicated OmniRoute Production Builder (Node 24 Engine)
# ==============================================================================
FROM node:24-bookworm-slim AS omniroute-builder

WORKDIR /omniroute

ENV GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV NEXT_TELEMETRY_DISABLED=1
ENV OMNIROUTE_USE_TURBOPACK=0
ENV NODE_OPTIONS="--max-old-space-size=4096"
ENV DISABLE_ESLINT_PLUGIN=true
ENV OMNIROUTE_BASE_PATH="/omniroute"
ENV NEXT_PUBLIC_OMNIROUTE_BASE_PATH="/omniroute"

ARG OMNIROUTE_REF=release/v3.8.50

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git python3 build-essential make g++ sqlite3 libsqlite3-dev curl \
 && update-ca-certificates --fresh \
 && git config --system http.sslCAInfo /etc/ssl/certs/ca-certificates.crt \
 && git config --system http.sslVerify true \
 && rm -rf /var/lib/apt/lists/*

COPY fix_omniroute.py /fix_omniroute.py

# Download OmniRoute release/v3.8.50, repair migration collisions, install dependencies, rebuild better-sqlite3, and run production build STRICTLY WITHOUT || true
RUN (git clone --depth 1 --branch "${OMNIROUTE_REF}" https://github.com/diegosouzapw/OmniRoute.git /omniroute || \
     (curl -sSL https://codeload.github.com/diegosouzapw/OmniRoute/tar.gz/refs/heads/${OMNIROUTE_REF} | tar -xz -C /omniroute --strip-components=1)) \
 && python3 /fix_omniroute.py /omniroute \
 && npm install --legacy-peer-deps --no-audit --no-fund \
 && npm rebuild better-sqlite3 --build-from-source \
 && OMNIROUTE_BASE_PATH="/omniroute" NEXT_PUBLIC_OMNIROUTE_BASE_PATH="/omniroute" NEXT_TELEMETRY_DISABLED=1 OMNIROUTE_USE_TURBOPACK=0 NODE_OPTIONS="--max-old-space-size=4096" npm run build \
 && touch /tmp/omniroute-build-complete

# ==============================================================================
# STAGE 2: Serialized Python AI Stack Builder (Executes ONLY after Stage 1 finishes)
# ==============================================================================
FROM debian:bookworm-slim AS python-builder

# FORCE BuildKit dependency serialization: COPY marker from omniroute-builder
COPY --from=omniroute-builder /tmp/omniroute-build-complete /tmp/

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev build-essential gcc g++ \
 && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU + Open WebUI + Utilities strictly WITHOUT || true
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu --break-system-packages \
 && pip3 install --no-cache-dir aiohttp pyrogram tgcrypto open-webui httpx uvicorn fastapi sentence-transformers --break-system-packages

# Pre-cache Open WebUI default embedding model inside build container
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# ==============================================================================
# STAGE 3: Multi-Service Production Runtime (Debian Bookworm)
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

# 3. Install Node.js 24 LTS Runtime into final container
RUN curl -fsSL https://nodejs.org/dist/v24.1.0/node-v24.1.0-linux-x64.tar.gz 2>/dev/null \
    || curl -fsSL https://nodejs.org/dist/v22.22.2/node-v22.22.2-linux-x64.tar.gz \
    | tar -xz -C /usr/local --strip-components=1

# 4. Copy pre-compiled OmniRoute production runtime from Stage 1
COPY --from=omniroute-builder /omniroute /omniroute

# 5. Copy pre-compiled Python packages and HuggingFace cache from Stage 2
COPY --from=python-builder /usr/local/lib/python3.11/dist-packages /usr/local/lib/python3.11/dist-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin
COPY --from=python-builder /root/.cache /root/.cache

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
