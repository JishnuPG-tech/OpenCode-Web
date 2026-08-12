# Architecture Specification: Opencode-Cli

This document details the software architecture, network routing, multi-service orchestration, and data persistence models for **Opencode-Cli** deployed on [Hugging Face Spaces (`Jishnupg/Opencode-Cli`)](https://huggingface.co/spaces/Jishnupg/Opencode-Cli).

---

## 1. System Overview

**Opencode-Cli** is an enterprise-grade multi-service web container running on Debian Bookworm Slim. It orchestrates six integrated services into a unified web application exposed via a single public ingress port (`4096`):

1. **FastAPI Reverse Proxy & Gateway Router**: Ingress path-routing, CORS, WebSocket proxying, and service isolation.
2. **Open WebUI**: Primary ChatGPT-style frontend pre-configured to use OmniRoute's dedicated API server (`127.0.0.1:20129/v1`).
3. **OmniRoute v3.8.50 Multi-Port AI Gateway**:
   - **Dashboard**: Port `20128` (Web UI & settings at `/omniroute`)
   - **Dedicated API Server**: Port `20129` (OpenAI `/v1` & Gemini `/v1beta` compatibility)
   - **Live WebSocket Server**: Port `20132` (Real-time monitoring)
4. **Redis Cache & Rate Limiter**: Port `6379` (In-memory cache and distributed rate limiting for OmniRoute).
5. **Jellyfin Media Server**: Port `8096` (Media streaming server at `/jellyfin`).
6. **Telegram 5G Stream Proxy**: Port `8080` (High-speed MTProto streaming daemon at `/tg-stream`).

---

## 2. Production Architecture Diagram

```mermaid
flowchart TD
    User([🌐 Public Web Client]) -->|HTTPS Port 443| Ingress[FastAPI Gateway Proxy - Port 4096]

    subgraph Container ["🐳 Docker Container (Debian Bookworm Slim)"]
        Ingress -->|Path: / | OWUI[Open WebUI - Port 8098]
        Ingress -->|Path: /omniroute/* | OmniDash[OmniRoute Dashboard - Port 20128]
        Ingress -->|Path: /v1 , /v1beta | OmniAPI[OmniRoute Dedicated API - Port 20129]
        Ingress -->|Path: /omniroute/live-ws/* | OmniWS[OmniRoute Live WS - Port 20132]
        Ingress -->|Path: /jellyfin/* | JF[Jellyfin Media Server - Port 8096]
        Ingress -->|Path: /tg-stream/* | TG[Telegram 5G Streamer - Port 8080]

        OWUI -->|Internal OpenAI API /v1| OmniAPI
        OmniDash -->|Distributed Cache & Limits| Redis[(Redis Server - Port 6379)]
        OmniAPI -->|Distributed Cache & Limits| Redis
        TG -->|Auto-Generate .strm Files| JF
    end

    subgraph Persistence ["💾 Persistence & Storage Model"]
        Ext4["Local Container Ext4 (/root/.omniroute)"] <-->|SQLite .backup API (Every 5 mins)| HFData["HF FUSE Persistent Mount (/data)"]
        OmniDash -->|Fast POSIX SQLite Locks| Ext4
        OWUI -->|User Accounts & DB| HFData
        JF -->|Media & Metadata| HFData
    end
```

---

## 3. Microservice Specifications

### 3.1 FastAPI Ingress Gateway (`proxy.py`, `gateway/`)
- **Port**: `4096` (Exposed as container entrypoint)
- **Role**:
  - Handles single-port ingress on Hugging Face Spaces.
  - Namespace path-routing with strict boundary enforcement.
  - Proxies HTTP requests and bidirectional WebSockets (`/ws/socket.io` & `/omniroute/live-ws`).

### 3.2 Open WebUI (`open-webui`)
- **Port**: `8098`
- **Path**: `/`
- **Environment**:
  - `OPENAI_API_BASE_URL="http://127.0.0.1:20129/v1"`
  - `ENABLE_OPENAI_API="true"`
  - `RAG_AUTO_UPDATE_INDEX="false"`
- **Optimization**: SentenceTransformer embeddings (`all-MiniLM-L6-v2`) pre-cached in Docker image for 1-second startup.

### 3.3 OmniRoute AI Gateway v3.8.50
- **Ports**:
  - **Dashboard**: `20128` (Path `/omniroute`)
  - **Dedicated API**: `20129` (Endpoints `/v1`, `/v1beta`)
  - **Live WebSocket**: `20132` (Path `/omniroute/live-ws`)
- **Environment**:
  - `OMNIROUTE_BASE_PATH="/omniroute"`
  - `REDIS_URL="redis://127.0.0.1:6379"`
  - `DATA_DIR="/root/.omniroute"`
- **Auto-Fix**: `fix_omniroute.py` auto-resolves numeric migration version collisions (e.g. version 143 collisions) at build time and container boot.

### 3.4 Redis Server (`redis-server`)
- **Port**: `6379`
- **Role**: In-memory rate limiting and distributed caching for OmniRoute.

### 3.5 Jellyfin Media Server (`jellyfin`)
- **Port**: `8096`
- **Path**: `/jellyfin`
- **Engine**: Jellyfin 10.11 + FFmpeg 5.1.

### 3.6 Telegram Direct Stream Proxy (`tg_streamer.py`)
- **Port**: `8080`
- **Path**: `/tg-stream`
- **Engine**: Python Pyrogram MTProto Client.

---

## 4. Port & Path Routing Matrix

| Public Request Path | Target Upstream Port | Target Service | Function |
| :--- | :--- | :--- | :--- |
| `/` | `8098` | Open WebUI | Main Web UI |
| `/omniroute/*` | `20128` | OmniRoute Dashboard | Management Panel |
| `/v1/*` | `20129` | OmniRoute API Server | Dedicated OpenAI API |
| `/v1beta/*` | `20129` | OmniRoute API Server | Dedicated Gemini API |
| `/omniroute/live-ws/*` | `20132` | OmniRoute WebSocket | Live Monitoring WS |
| `/jellyfin/*` | `8096` | Jellyfin Media Server | Media Streaming |
| `/tg-stream/*` | `8080` | TG Stream Proxy | Telegram Direct Streamer |

---

## 5. Storage & Persistence Model

- **Active Execution (`/root/.omniroute/storage.sqlite`)**: Runs on local Ext4 container disk to support `better-sqlite3` POSIX file locking.
- **Safe SQLite Backup (`/data/omniroute/storage.sqlite`)**: Background daemon uses `sqlite3 .backup` API every 5 minutes and on shutdown to write consistent snapshots to the HF FUSE mount.

---

## 6. Repository File Structure

```
.
├── Dockerfile              # Multi-stage Docker image with Redis & pre-cached models
├── ARCHITECTURE.md         # Architecture specification (this document)
├── README.md               # User quickstart guide
├── entrypoint.sh           # Concurrent service startup, Redis daemon & SQLite backup
├── fix_omniroute.py        # Migration version collision auto-repair script
├── nginx.conf              # Nginx configuration reference
├── proxy.py                # FastAPI gateway entrypoint script
├── tg_streamer.py          # Pyrogram Telegram 5G stream proxy
└── gateway/                # FastAPI Modular Router Package
    ├── __init__.py
    ├── main.py             # App router aggregator
    ├── utils.py            # Async HTTP & WebSocket proxy engine
    ├── openwebui.py        # Open WebUI path routing
    ├── omniroute.py        # OmniRoute API & asset routing
    ├── jellyfin.py         # Jellyfin path routing
    └── tg_stream.py        # Telegram proxy routing
```
