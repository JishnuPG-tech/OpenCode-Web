# OpenCode Space — Production System Architecture & Design Specification

This document provides a comprehensive technical overview of the **`Jishnupg/Opencode-Cli`** multi-service gateway architecture, service discovery, database persistence model, security boundaries, and protocol proxies.

---

## 1. System Ingress Topology & Port Matrix

All client traffic terminates at **Port 4096** (the exposed public port on Hugging Face Spaces). The system operates a dual-layer reverse proxy architecture to guarantee sub-second platform readiness and unified routing.

```
                                  [🌐 Public Internet Client]
                                               │
                                 [Nginx Edge Proxy (Port 4096)]
                                               │
                                 [FastAPI Master Gateway (:8000)]
                                               │
  ┌──────────────────┬─────────────────────────┼────────────────────────┬──────────────────┐
  │                  │                         │                        │                  │
[Open WebUI]  [OmniRoute Dashboard]   [OmniRoute Dedicated API] [Jellyfin Media]  [TG 5G Streamer]
(Port 8098)    (Port 20128)             (Port 20129)             (Port 8096)        (Port 8080)
  Path: /       Path: /dashboard         Path: /v1, /v1beta       Path: /jellyfin    Path: /tg-stream
```

### Complete Ingress Routing Matrix

| Ingress Path / Pattern | Upstream Host:Port | Microservice | Protocol / Handler | Header Sanitization |
| :--- | :--- | :--- | :--- | :--- |
| `GET /health/live` | Internal Gateway | FastAPI Gateway | Native ASGI JSON | Instant 200 OK (<1ms) |
| `/` (Default Fallback) | `127.0.0.1:8098` | Open WebUI | HTTP / Socket.IO WS | HTML base rewrite (`/`) |
| `/omniroute`, `/omniroute/`| `127.0.0.1:8000` | FastAPI Gateway | HTTP 307 Redirect | Redirects to `/dashboard` |
| `/dashboard/*` | `127.0.0.1:20128` | OmniRoute Dashboard | HTTP / Next.js SSR | Strip X-Frame-Options |
| `/v1/*`, `/api/v1/*` | `127.0.0.1:20129` | Dedicated OpenAI API | OpenAI SSE Stream | CORS `*`, `Host` forward |
| `/v1beta/*`, `/api/v1beta/*`| `127.0.0.1:20129` | Dedicated Gemini API | Gemini JSON / Stream | CORS `*`, `Host` forward |
| `/api/providers/*` | `127.0.0.1:20128` | OmniRoute Management | REST JSON API | Encrypted DB read |
| `/api/custom-models/*` | `127.0.0.1:20128` | OmniRoute Management | REST JSON API | Referer-based proxy |
| `/api/connections/*` | `127.0.0.1:20128` | OmniRoute Management | REST JSON API | Referer-based proxy |
| `/api/oauth/*` | `127.0.0.1:20128` | OmniRoute OAuth | Remote OAuth Flow | `ALLOW_REMOTE_OAUTH` |
| `/live-ws/*` | `127.0.0.1:20132` | Live Telemetry WS | WebSocket Stream | `Host`, `X-Forwarded-*` |
| `/jellyfin/*` | `127.0.0.1:8096` | Jellyfin Media Server | Range Video / HTTP | `X-Forwarded-Prefix` |
| `/tg-stream/*`, `/tg_stream/*`| `127.0.0.1:8080` | Pyrogram 5G Streamer | 5G Chunk Streamer | Direct Pyrogram Stream |

---

## 2. Gateway Core Engine Architecture (`gateway/`)

The master gateway (`gateway/main.py`, `gateway/utils.py`, `gateway/omniroute.py`) provides intelligent request classification and routing.

```
                           [Incoming HTTP Request]
                                      │
                         [Security Path Traversal Check]
                                      │
                        [Lightweight Probe /health/live?] ──(Yes)──> 200 OK
                                      │ (No)
                         [Referer Header Inspection]
                        /                                \
           (Referer has /dashboard)            (No OmniRoute Referer)
                      │                                    │
           [Route to OmniRoute :20128]             [Match Path Prefix Matrix]
                                                  /        │         \
                                        (OmniRoute)   (Jellyfin)  (TG Stream)
                                            │              │           │
                                         [:20128]       [:8096]     [:8080]
                                                           │
                                                  [Default Fallback]
                                                           │
                                                    [Open WebUI :8098]
```

### Key Gateway Design Patterns:
1. **Async Connection Pooling (`httpx.AsyncClient`)**: Managed via FastAPI `@asynccontextmanager` lifespan. Connection keep-alive prevents TCP handshake overhead across internal microservice proxies.
2. **Referer-Aware Routing**: Requests originating from OmniRoute UI pages (`Referer` containing `/dashboard` or `/omniroute`) are routed directly to OmniRoute port `20128`. This prevents auxiliary requests (`/api/custom-models`, `/api/connections`, `/providers/*.svg`) from falling through to Open WebUI.
3. **CORS & iFrame Security Normalization**: Automatically strips restrictive `X-Frame-Options` headers and injects `Content-Security-Policy: frame-ancestors 'self' https://huggingface.co https://*.hf.space;` to enable embedding on Hugging Face Spaces.

---

## 3. Storage Persistence & SQLite Synchronization Model

OmniRoute uses `better-sqlite3`. To bypass FUSE network drive lock limitations while maintaining persistence, a dual-layer storage architecture is implemented:

```
┌──────────────────────────────────────────────┐     120s Cron Daemon /      ┌──────────────────────────────────────────────┐
│  High-Speed Ext4 Container Disk              │     Shutdown Backup Loop    │  Persistent Volume Mount                      │
│  (/root/.omniroute/storage.sqlite)           ├────────────────────────────>│  (/data/omniroute/storage.sqlite)            │
│  - Active runtime POSIX file locks (fcntl)   │                             │  - Persistent across Space rebuilds & sleep   │
│  - Active WAL (-wal) & SHM (-shm) sidecars   │<────────────────────────────┤  - Rotating backups (/data/omniroute/backups) │
└──────────────────────────────────────────────┘     Boot Restoration Sync   └──────────────────────────────────────────────┘
```

### Database Lifecycle & Safety Guarantees:
1. **Boot Initialization**:
   - `entrypoint.sh` checks for persistent snapshot at `/data/omniroute/storage.sqlite`.
   - Validates integrity using `sqlite3 "PRAGMA quick_check;"`.
   - Restores clean snapshot into `/root/.omniroute/storage.sqlite`.
2. **Runtime Backup Loop**:
   - Every 120 seconds, a background daemon executes `sync_omniroute_db()`.
   - Issues `PRAGMA wal_checkpoint(PASSIVE);` and `sqlite3 .backup`.
   - Syncs `-wal` and `-shm` sidecars to preserve uncommitted transactions.
   - Rotates up to 5 rolling backups in `/data/omniroute/backups/storage-YYYYMMDD-HHMM.sqlite`.
3. **Shutdown Hook**:
   - Shell traps (`trap sync_omniroute_db EXIT INT TERM`) flush runtime state before container termination.

---

## 4. Encryption & Security Model

- **AES-256-GCM Encryption**: All provider credentials (API keys, OAuth access tokens, refresh tokens) are encrypted at rest with `STORAGE_ENCRYPTION_KEY`.
- **Secrets Fallback Engine**: If secrets are not passed via Hugging Face Space Secrets during local development, safe default fallbacks prevent container crash:
  - `STORAGE_ENCRYPTION_KEY`
  - `JWT_SECRET`
  - `API_KEY_SECRET`
  - `INITIAL_PASSWORD`
- **Path Traversal Gate**: The gateway inspects all requested paths and rejects directory traversal patterns (`..`, `.env`, `.sqlite`, `.git`) with HTTP 403.

---

## 5. Process Lifecycle & Self-Healing Supervisor

The container supervisor (`entrypoint.sh`) maintains 24/7 uptime for all background daemons:

```
                        [PID 1 Process Supervisor Loop]
                                       │ (every 5s)
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
 [Kill -0 $FASTAPI_PID]        [Kill -0 $NGINX_PID]        [Kill -0 $OMNIROUTE_PID]
         │                             │                             │
    (Dead? Restart)               (Dead? Restart)               (Dead? Restart)
 python3 -m uvicorn proxy:app    nginx -g 'daemon off;'      cd /omniroute && node server.js
```

- **Fast Gateway Readiness**: FastAPI (`:8000`) and Nginx (`:4096`) start within **300ms**, allowing Hugging Face to report `RUNNING` status instantly.
- **Asynchronous Heavy Boot**: OmniRoute Next.js server, Open WebUI, Jellyfin, and TG Streamer initialize in parallel background tasks without blocking public ingress.
