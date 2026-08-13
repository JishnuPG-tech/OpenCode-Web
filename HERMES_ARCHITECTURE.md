# 🔒 Hermes Agent Framework Production Architecture & Fix Documentation

This document serves as the **locked, definitive reference** for the Hermes Agent integration on the Hugging Face Space (`https://jishnupg-opencode-cli.hf.space/hermes`).

> [!CAUTION]
> **DO NOT MODIFY OR REVERT THE HERMES CONFIGURATION, PORT BINDING, OR ROUTING DESCRIBED IN THIS FILE.**
> All solutions below were empirically verified live via container logs and HTTP 200 OK status checks.

---

## 🏗️ Architecture & Port Matrix

| Service | Host & Port | Ingress Path | Function |
|---|---|---|---|
| **Hermes Agent Server** | `127.0.0.1:8642` | `/hermes/*` | Autonomous AI agent API & gateway |
| **OmniRoute LLM Brain** | `127.0.0.1:20129` | `/v1/*` | Multi-model provider routing engine |
| **FastAPI Gateway** | `127.0.0.1:8000` | `/` | Ingress router, auth proxy & health supervisor |

---

## 🛠️ Summary of Root Causes & Permanent Solutions

### 1. Hermes Gateway CLI Command & Port Parameter Fix
- **Problem**: Passing `--port 8642` as a CLI argument to `hermes gateway run` caused `hermes: error: unrecognized arguments: --port 8642` and crashed the process.
- **Solution in [`entrypoint.sh`](file:///c:/Users/JISHNU%20PG/Music/InstaFlow/Opencode-Cli/entrypoint.sh)**:
  - Configured port `8642` via environment variables (`API_SERVER_PORT=8642`, `API_SERVER_HOST=127.0.0.1`, `API_SERVER_ENABLED=true`, `HERMES_GATEWAY_PORT=8642`).
  - Executed `hermes gateway` without invalid CLI argument flags.

### 2. Zero-Touch Configuration Injection (`.env` & `config.json`)
- **Problem**: `hermes-agent` required interactive CLI setup prompts on first boot.
- **Solution in [`entrypoint.sh`](file:///c:/Users/JISHNU%20PG/Music/InstaFlow/Opencode-Cli/entrypoint.sh)**:
  - Pre-creates `/root/.hermes/.env` and `/root/.hermes/config.json` before launch:
    ```json
    {
      "api_base_url": "http://127.0.0.1:20129/v1",
      "api_key": "omniroute",
      "model": "claude-sonnet-4-6",
      "data_dir": "/root/.hermes",
      "api_server": {
        "enabled": true,
        "port": 8642,
        "host": "127.0.0.1"
      }
    }
    ```

### 3. Gateway Status & Discovery Endpoint (`/hermes`, `/hermes/v1`)
- **Problem**: Visiting `/hermes` or `/hermes/v1` in a browser previously returned `404 Not Found` because the Hermes backend API server only exposes specific REST sub-paths (`/v1/models`, `/v1/chat/completions`, `/health`).
- **Solution in [`gateway/hermes.py`](file:///c:/Users/JISHNU%20PG/Music/InstaFlow/Opencode-Cli/gateway/hermes.py)**:
  - Added a root JSON status handler for `/hermes`, `/hermes/`, `/hermes/v1`, and `/hermes/v1/` returning HTTP `200 OK` with service capabilities and endpoint discovery details.
  - Proxies functional sub-paths (`/hermes/v1/models`, `/hermes/v1/chat/completions`, `/hermes/health`) directly to `http://127.0.0.1:8642`.

### 4. Persistent Memory & Skills Backup Model
- **Runtime Directory**: `/root/.hermes/`
- **Persistent Storage Mount**: `/data/hermes/`
- **Sync Daemon**: Background 15-second rsync daemon in `entrypoint.sh` syncs memories (`MEMORY.md`, `USER.md`), custom skills (`skills/`), and SQLite chat history (`sessions/`) to `/data/hermes/`.
- **Boot Restoration**: Restores persistent data from `/data/hermes/` into `/root/.hermes/` on startup.

---

## 🔒 Mandatory Locking Rules for AI Assistants
1. **DO NOT** change `HERMES_PORT` or `API_SERVER_PORT` away from `8642`.
2. **DO NOT** pass `--port` to the `hermes gateway` CLI command string.
3. **DO NOT** change `api_base_url` away from `http://127.0.0.1:20129/v1`.
4. **DO NOT** remove `/data/hermes` persistent volume backup logic in `entrypoint.sh`.

---

## 📱 Client Connection Guide

### Mobile / Android APK Connection
- **Base URL**: `https://jishnupg-opencode-cli.hf.space/hermes/v1`
- **API Key**: `<your HERMES_GATEWAY_API_KEY secret>`
- **Models Endpoint**: `https://jishnupg-opencode-cli.hf.space/hermes/v1/models`
- **Completions Endpoint**: `https://jishnupg-opencode-cli.hf.space/hermes/v1/chat/completions`

### Local CLI / Termux (`hermes setup`)
```bash
hermes setup
# Provider: OpenAI-compatible
# Base URL: https://jishnupg-opencode-cli.hf.space/v1
# API Key:  key_oute_xxxxxxxxxxxx (from OmniRoute dashboard)
```
