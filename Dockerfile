# ==============================================================================
# STAGE 1: OmniRoute Production Builder (isolated, Node 24)
# Answers the question: can OmniRoute v3.8.50 compile alone?
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

# ── Step 1: Fetch source (git clone with tarball fallback) ──────────────────
RUN git clone --depth 1 --branch "${OMNIROUTE_REF}" \
        https://github.com/diegosouzapw/OmniRoute.git /omniroute \
 || (curl -sSL "https://codeload.github.com/diegosouzapw/OmniRoute/tar.gz/refs/heads/${OMNIROUTE_REF}" \
     | tar -xz -C /omniroute --strip-components=1)

# ── Step 2: Repair migration version collisions ─────────────────────────────
RUN python3 /fix_omniroute.py /omniroute

# ── Step 3: Install npm dependencies ────────────────────────────────────────
RUN npm install --legacy-peer-deps --no-audit --no-fund

# ── Step 4: Build better-sqlite3 native bindings ────────────────────────────
RUN npm rebuild better-sqlite3 --build-from-source

# ── Step 5: Next.js production build (the expensive step) ───────────────────
RUN OMNIROUTE_BASE_PATH="/omniroute" \
    NEXT_PUBLIC_OMNIROUTE_BASE_PATH="/omniroute" \
    NEXT_TELEMETRY_DISABLED=1 \
    OMNIROUTE_USE_TURBOPACK=0 \
    NODE_OPTIONS="--max-old-space-size=4096" \
    npm run build

# ── Step 6: Explicit success markers visible in build log ───────────────────
RUN echo "===== OMNIROUTE BUILD COMPLETE =====" \
 && du -sh .next/ 2>/dev/null || du -sh .build/ 2>/dev/null || echo "[WARN] Could not measure build output" \
 && touch /tmp/omniroute-build-complete

# ==============================================================================
# STAGE 2: Python / Open WebUI Builder
# Cannot start until Stage 1 fully completes (marker dependency).
# ==============================================================================
FROM debian:bookworm-slim AS python-builder

# BuildKit dependency edge — Stage 2 WAITS for Stage 1 to fully complete.
COPY --from=omniroute-builder /tmp/omniroute-build-complete /tmp/omniroute-build-complete

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev build-essential gcc g++ \
 && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir torch \
    --index-url https://download.pytorch.org/whl/cpu \
    --break-system-packages

RUN pip3 install --no-cache-dir \
    aiohttp pyrogram tgcrypto open-webui httpx uvicorn fastapi sentence-transformers \
    --break-system-packages

RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

RUN echo "===== PYTHON BUILD COMPLETE =====" \
 && touch /tmp/python-build-complete

# ==============================================================================
# STAGE 3: Jellyfin + FFmpeg Builder
# Cannot start until Stage 2 (and therefore Stage 1) fully completes.
# ==============================================================================
FROM debian:bookworm-slim AS jellyfin-builder

# BuildKit dependency edge — Stage 3 WAITS for Stage 2 to fully complete.
COPY --from=python-builder /tmp/python-build-complete /tmp/python-build-complete

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/jellyfin.gpg arch=amd64] https://repo.jellyfin.org/debian bookworm main" > /etc/apt/sources.list.d/jellyfin.list \
 && apt-get update && apt-get install -y --no-install-recommends jellyfin-server jellyfin-web ffmpeg \
 && rm -rf /var/lib/apt/lists/*

RUN echo "===== JELLYFIN BUILD COMPLETE =====" \
 && touch /tmp/jellyfin-build-complete

# ==============================================================================
# STAGE 4: Final Multi-Service Production Runtime
# Assembles artifacts from all three prior stages sequentially.
# ==============================================================================
FROM debian:bookworm-slim

ENV XDG_DATA_HOME=/data/share
ENV XDG_CONFIG_HOME=/data/config
ENV XDG_CACHE_HOME=/root/.cache
ENV XDG_STATE_HOME=/data/state
ENV HOME=/root

# BuildKit dependency edge — runtime starts AFTER all three builders complete.
COPY --from=jellyfin-builder /tmp/jellyfin-build-complete /tmp/jellyfin-build-complete

# 1. Minimal system runtime dependencies & Redis
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git python3 python3-pip \
    nginx gnupg lsb-release \
    build-essential make g++ sqlite3 libsqlite3-dev \
    redis-server \
 && rm -rf /var/lib/apt/lists/*

# 2. Copy Jellyfin server binaries & FFmpeg from Stage 3
COPY --from=jellyfin-builder /usr/bin/jellyfin* /usr/bin/
COPY --from=jellyfin-builder /usr/share/jellyfin /usr/share/jellyfin
COPY --from=jellyfin-builder /usr/lib/jellyfin* /usr/lib/
COPY --from=jellyfin-builder /usr/bin/ffmpeg /usr/bin/ffmpeg
COPY --from=jellyfin-builder /usr/bin/ffprobe /usr/bin/ffprobe

# 3. Copy Node 24 runtime from Stage 1 (no manual curl download needed)
COPY --from=omniroute-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=omniroute-builder /usr/local/bin/npm  /usr/local/bin/npm
COPY --from=omniroute-builder /usr/local/bin/npx  /usr/local/bin/npx
COPY --from=omniroute-builder /usr/local/lib/node_modules /usr/local/lib/node_modules

# 4. Copy pre-compiled OmniRoute production runtime from Stage 1
COPY --from=omniroute-builder /omniroute /omniroute

# 5. Copy Python packages and HuggingFace model cache from Stage 2
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
