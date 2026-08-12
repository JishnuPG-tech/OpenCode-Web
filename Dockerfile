# ==============================================================================
# STAGE 1: OmniRoute Production Builder (Node 24)
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

# Clone, fix migrations, install deps, build — STRICTLY NO || true at any step
RUN (git clone --depth 1 --branch "${OMNIROUTE_REF}" https://github.com/diegosouzapw/OmniRoute.git /omniroute || \
     (curl -sSL "https://codeload.github.com/diegosouzapw/OmniRoute/tar.gz/refs/heads/${OMNIROUTE_REF}" \
      | tar -xz -C /omniroute --strip-components=1)) \
 && python3 /fix_omniroute.py /omniroute \
 && npm install --legacy-peer-deps --no-audit --no-fund \
 && npm rebuild better-sqlite3 --build-from-source \
 && OMNIROUTE_BASE_PATH="/omniroute" NEXT_PUBLIC_OMNIROUTE_BASE_PATH="/omniroute" \
    NEXT_TELEMETRY_DISABLED=1 OMNIROUTE_USE_TURBOPACK=0 \
    NODE_OPTIONS="--max-old-space-size=4096" npm run build \
 && touch /tmp/omniroute-build-complete

# ==============================================================================
# STAGE 2: Python / Open WebUI Builder
# Depends explicitly on Stage 1 so BuildKit cannot run these stages concurrently.
# ==============================================================================
FROM debian:bookworm-slim AS python-builder

# This COPY creates the BuildKit dependency edge: Stage 2 CANNOT start until
# Stage 1's entire build (including npm run build) has completed.
COPY --from=omniroute-builder /tmp/omniroute-build-complete /tmp/omniroute-build-complete

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev build-essential gcc g++ \
 && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU wheel first (large, isolated step)
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu --break-system-packages

# Install Open WebUI and all remaining Python dependencies — STRICTLY NO || true
RUN pip3 install --no-cache-dir \
    aiohttp pyrogram tgcrypto open-webui httpx uvicorn fastapi sentence-transformers \
    --break-system-packages

# Pre-cache default embedding model so the container starts in ~1 second
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Serialization marker so Stage 3 can depend on Stage 2
RUN touch /tmp/python-build-complete

# ==============================================================================
# STAGE 3: Final Multi-Service Production Runtime
# Depends explicitly on Stage 2 (which depends on Stage 1), so the runtime stage
# starts only after BOTH heavy build stages have fully completed.
# ==============================================================================
FROM debian:bookworm-slim

ENV XDG_DATA_HOME=/data/share
ENV XDG_CONFIG_HOME=/data/config
ENV XDG_CACHE_HOME=/root/.cache
ENV XDG_STATE_HOME=/data/state
ENV HOME=/root

# ── IMPORTANT: This COPY establishes the BuildKit dependency chain: ────────────
# Stage 3 cannot execute ANY of its RUN commands (including Jellyfin install)
# until Stage 2 is completely finished (which waited for Stage 1 to finish).
COPY --from=python-builder /tmp/python-build-complete /tmp/python-build-complete

# 1. Install system dependencies & Redis
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git python3 python3-pip \
    nginx gnupg lsb-release \
    build-essential make g++ sqlite3 libsqlite3-dev \
    redis-server \
 && rm -rf /var/lib/apt/lists/*

# 2. Install Jellyfin & FFmpeg (runs AFTER OmniRoute and Python builds complete)
RUN mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/jellyfin.gpg arch=amd64] https://repo.jellyfin.org/debian bookworm main" > /etc/apt/sources.list.d/jellyfin.list \
 && apt-get update && apt-get install -y --no-install-recommends jellyfin-server jellyfin-web ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# 3. Copy Node 24 runtime from Stage 1 (avoids broken manual download)
COPY --from=omniroute-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=omniroute-builder /usr/local/bin/npm  /usr/local/bin/npm
COPY --from=omniroute-builder /usr/local/bin/npx  /usr/local/bin/npx
COPY --from=omniroute-builder /usr/local/lib/node_modules /usr/local/lib/node_modules

# 4. Copy pre-compiled OmniRoute production runtime from Stage 1
COPY --from=omniroute-builder /omniroute /omniroute

# 5. Copy Python site-packages and HuggingFace model cache from Stage 2
COPY --from=python-builder /usr/local/lib /usr/local/lib
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
