# Architecture Specification: Opencode-Cli

This document details the software architecture, network routing, multi-service orchestration, and data persistence models for **Opencode-Cli** deployed on [Hugging Face Spaces (`Jishnupg/Opencode-Cli`)](https://huggingface.co/spaces/Jishnupg/Opencode-Cli).

---

## 1. System Overview

**Opencode-Cli** is a multi-service web container running on Debian Bookworm. It bundles five core microservices into a unified web application exposed via a single public port (`4096`):

1. **FastAPI Reverse Proxy & Gateway Router**: Ingress routing, path-rewriting, HTML asset fixing, CORS, and WebSocket streaming.
2. **Open WebUI**: Primary ChatGPT-style web interface. Pre-configured with OmniRoute as its backend OpenAI API provider.
3. **OmniRoute AI Gateway**: Universal AI model routing, combo load balancing, fallback rules, circuit breakers, and OpenAI (`/v1`) & Gemini (`/v1beta`) API compatibility.
4. **Jellyfin Media Server**: Media streaming center.
5. **Telegram 5G Stream Proxy**: High-speed MTProto streaming daemon that converts Telegram files into `.strm` media files for Jellyfin.

---

## 2. System Architecture Diagram

```mermaid
flowchart TD
    User([🌐 Public Web Client]) -->|HTTPS Port 443| Ingress[FastAPI Gateway Proxy - Port 4096]

    subgraph Container ["🐳 Docker Container (Debian Bookworm Slim)"]
        Ingress -->|Path: / | OWUI[Open WebUI - Port 8098]
        Ingress -->|Path: /omniroute | Omni[OmniRoute AI Gateway - Port 20128]
        Ingress -->|Path: /v1 , /v1beta | Omni
        Ingress -->|Path: /jellyfin | JF[Jellyfin Media Server - Port 8096]
        Ingress -->|Path: /tg-stream | TG[Telegram 5G Stream Proxy - Port 8080]

        OWUI -->|OpenAI API Format /v1| Omni
        TG -->|Auto-Generate .strm Files| JF
    end

    subgraph Persistence ["💾 Persistence Architecture"]
        Ext4["Local Container Ext4 (/root/.omniroute)"] <-->|Auto-Sync Daemon (25s)| HFData["HF FUSE Persistent Mount (/data)"]
        Omni -->|POSIX SQLite Locks| Ext4
        OWUI -->|User DB & Configs| HFData
        JF -->|Media & Metadata| HFData
    end
```

---

## 3. Microservice Specifications

### 3.1 FastAPI Ingress Gateway (`proxy.py`, `gateway/`)
- **Port**: `4096` (Exposed as container entrypoint)
- **Role**:
  - Handles single-port ingress on Hugging Face Spaces.
  - Dynamically routes requests based on URL path prefixes.
  - Rewrites HTML `<head>` tags and Next.js asset paths (`/_next`).
  - Proxies HTTP requests and bidirectional WebSockets (`/ws/socket.io`).

### 3.2 Open WebUI (`open-webui`)
- **Port**: `8098`
- **Path**: `/`
- **Environment**:
  - `OPENAI_API_BASE_URL="http://127.0.0.1:20128/v1"`
  - `ENABLE_OPENAI_API="true"`
  - `RAG_AUTO_UPDATE_INDEX="false"`
- **Optimization**: SentenceTransformer embeddings (`all-MiniLM-L6-v2`) are pre-baked into the Docker image cache to allow instant boot in **~1s**.

### 3.3 OmniRoute AI Gateway (`/omniroute`)
- **Port**: `20128`
- **Path**: `/omniroute` *(Redirects to `/omniroute/dashboard`)*
- **API Endpoints**: `/v1` (OpenAI format), `/v1beta` (Gemini format), and 21 specific backend management routes (`/api/providers`, `/api/combos`, etc.).
- **Engine**: Node.js 22 LTS + Next.js.
- **Auto-Fix**: `fix_omniroute.py` auto-resolves numeric migration version collisions (e.g., version 143 collisions) at build time and container boot.

### 3.4 Jellyfin Media Server (`jellyfin`)
- **Port**: `8096`
- **Path**: `/jellyfin`
- **Data Location**: `/data/jellyfin/data`, `/data/jellyfin/media/Movies`
- **Engine**: Jellyfin 10.11 + FFmpeg 5.1.

### 3.5 Telegram Direct Stream Proxy (`tg_streamer.py`)
- **Port**: `8080`
- **Path**: `/tg-stream`
- **Engine**: Python Pyrogram MTProto Client.
- **Function**: Automatically syncs Telegram channel media into `.strm` files inside Jellyfin's movie directory.

---

## 4. Port & Path Routing Matrix

| Public Request Path | Target Upstream Port | Target Service | Function |
| :--- | :--- | :--- | :--- |
| `/` | `8098` | Open WebUI | Main Web UI |
| `/openwebui/*` | `8098` | Open WebUI | WebUI Assets |
| `/omniroute` | `20128` | OmniRoute AI Gateway | Management Dashboard |
| `/omniroute/_next/*` | `20128` | OmniRoute AI Gateway | Next.js Static Assets |
| `/v1/*` | `20128` | OmniRoute AI Gateway | OpenAI API Endpoint |
| `/v1beta/*` | `20128` | OmniRoute AI Gateway | Gemini API Endpoint |
| `/api/providers`, `/api/combos`, ... | `20128` | OmniRoute AI Gateway | OmniRoute Management APIs |
| `/api/config`, `/api/v1/*` | `8098` | Open WebUI | Open WebUI Core APIs |
| `/jellyfin/*` | `8096` | Jellyfin Media Server | Media Streaming |
| `/tg-stream/*` | `8080` | TG Stream Proxy | Telegram Direct Streamer |

---

## 5. Storage & Persistence Model

```
                    ┌──────────────────────────────────────────────┐
                    │     Hugging Face Network Mount (/data)       │
                    │   (FUSE Volume - Persistent Across Boots)   │
                    └──────────────────────┬───────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        │                                     │
             ┌──────────▼──────────┐               ┌──────────▼──────────┐
             │ /data/open-webui    │               │ /data/omniroute     │
             │ (webui.db)          │               │ (storage.sqlite)    │
             └─────────────────────┘               └──────────▲──────────┘
                                                              │
                                                   (Background Sync 25s)
                                                              │
                                                   ┌──────────┴──────────┐
                                                   │ /root/.omniroute    │
                                                   │ (Active Local Ext4) │
                                                   └─────────────────────┘
```

- **HF FUSE Mount (`/data`)**: Persistent volume provided by Hugging Face Spaces.
- **Local Ext4 Disk (`/root/.omniroute`)**: Stores OmniRoute's active `better-sqlite3` database file to prevent SQLite `disk I/O error` on FUSE mounts.
- **Background Sync Daemon**: Runs every 25 seconds in `entrypoint.sh` to copy `/root/.omniroute/storage.sqlite` and `server.env` to `/data/omniroute/`.

---

## 6. Repository File Structure

```
.
├── Dockerfile              # Multi-stage Docker image build
├── ARCHITECTURE.md         # Architecture specification (this file)
├── README.md               # User quickstart guide
├── entrypoint.sh           # Concurrent service startup & storage sync daemon
├── fix_omniroute.py        # Migration version collision auto-repair script
├── nginx.conf              # Nginx configuration (optional reference)
├── proxy.py                # FastAPI gateway entrypoint script
├── tg_streamer.py          # Pyrogram Telegram 5G stream proxy
├── index.html              # Custom splash landing page
└── gateway/                # FastAPI Modular Router Package
    ├── __init__.py
    ├── main.py             # App router aggregator
    ├── utils.py            # Async HTTP & WebSocket proxy engine
    ├── openwebui.py        # Open WebUI path routing
    ├── omniroute.py        # OmniRoute API & asset routing
    ├── jellyfin.py         # Jellyfin path routing
    └── tg_stream.py        # Telegram proxy routing
```
