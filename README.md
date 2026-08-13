---
title: Opencode CLI
emoji: 🖥️
colorFrom: green
colorTo: blue
sdk: docker
app_port: 4096
pinned: false
---

<div align="center">

# 🚀 OpenCode CLI & Multi-Service AI Gateway

**Enterprise Multi-Service AI, Autonomous Agent, and Streaming Container Hub**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-ContainerIZED-blue.svg)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![Node.js](https://img.shields.io/badge/Node.js-v20-339933.svg)](https://nodejs.org/)
[![Next.js](https://img.shields.io/badge/Next.js-v16-000000.svg)](https://nextjs.org/)

[Features](#-key-features) • [Architecture](#-architecture) • [Port Matrix](#-port--ingress-matrix) • [Quick Start](#-quick-start) • [Client Setup](#-client-integration-guides) • [Documentation](#-documentation)

</div>

---

## 🌟 Project Overview

**OpenCode CLI** is a production-grade, multi-service Docker container hub combining an OpenAI-compatible LLM router (**OmniRoute**), an autonomous self-improving AI agent (**Hermes Agent**), a modern chat UI (**Open WebUI**), a media server (**Jellyfin**), and a high-speed video streamer (**Telegram Drive Proxy**), all orchestrated behind a unified FastAPI & Nginx reverse proxy with persistent storage synchronization.

---

## 🏗️ Architecture

```mermaid
graph TD
    Client[📱 Clients / Mobile APK / Web Browser / Telegram] -->|HTTPS :4096| Nginx[🌐 Nginx Reverse Proxy]
    Nginx -->|Proxy /| FastAPI[⚡ FastAPI Master Gateway :8000]

    FastAPI -->|Proxy /v1/*| OmniRoute[🧠 OmniRoute AI Gateway :20129]
    FastAPI -->|Proxy /hermes/*| Hermes[🤖 Hermes Agent Framework :8642]
    FastAPI -->|Proxy /_app, /api| OpenWebUI[💬 Open WebUI :8098]
    FastAPI -->|Proxy /jellyfin| Jellyfin[🎬 Jellyfin Server :8096]
    FastAPI -->|Proxy /tg-stream| TGStream[⚡ Telegram Streamer]

    OmniRoute -->|LLM Backend| ExternalLLM[☁️ Cloud Providers / OpenAI / Anthropic / Gemini]
    Hermes -->|API Calling| OmniRoute

    subgraph Persistence Layer [/data Volume]
        OmniRouteDB[(storage.sqlite)]
        WebUIDB[(webui.db)]
        HermesMemory[(Hermes Memory & Skills)]
    end

    OmniRoute -.->|15s Snapshot| OmniRouteDB
    OpenWebUI -.->|15s Snapshot| WebUIDB
    Hermes -.->|15s rsync| HermesMemory
```

---

## ✨ Key Features

### 🧠 1. OmniRoute AI Gateway (`/v1`, `/dashboard`)
- **Multi-Provider Load Balancer**: Route prompts across OpenAI, Anthropic, Gemini, DeepSeek, Groq, and custom endpoints.
- **Model Fallback & Combos**: Dynamic candidate pools and automatic retry failovers.
- **Embedded Dashboard**: Manage API keys, provider credentials, and token usage analytics.

### 🤖 2. Hermes Autonomous Agent Framework (`/hermes/v1`)
- **Nous Research Engine**: Autonomous tool-calling agent with native web search, web page extraction, and browser automation.
- **Persistent Memory & Self-Improving Skills**: Automatically learns user preferences (`USER.md`), facts (`MEMORY.md`), and generates python skills (`skills/`).
- **OpenAI-Compatible Endpoint**: Exposes `/hermes/v1/chat/completions` and `/hermes/v1/models` for mobile APKs, Termux, and OpenAI SDKs.

### 💬 3. Open WebUI (`/`)
- **Modern AI Chat Interface**: Multi-modal chat, code highlighting, artifact previews, and prompt templates.
- **Persistent Workspace**: Stores chats, custom prompts, and settings securely.

### 🎬 4. Jellyfin Media Server (`/jellyfin/`)
- **Personal Media Streaming**: Stream movies, TV shows, and audio directly from persistent storage.

### ⚡ 5. Telegram Stream Proxy (`/tg-stream/`)
- **High-Speed Range Streamer**: Stream video files directly from Telegram channels using chunked HTTP range requests.

### 🛡️ 6. Self-Healing & Persistence Supervisor
- **PID 1 Supervisor**: Auto-restarts any crashed background service within 5 seconds.
- **Integrity Validation**: Periodic background snapshotting to `/data/` persistent volumes.

---

## 📊 Port & Ingress Matrix

| Microservice | Internal Port | External Route | Status Health Check |
|---|---|---|---|
| **Public Gateway** | `:4096` / `:8000` | `/` | `GET /health/live` |
| **Open WebUI** | `:8098` | `/` | `GET /health` |
| **OmniRoute API Bridge** | `:20129` | `/v1/*` | `GET /v1/models` |
| **OmniRoute Dashboard** | `:20128` | `/dashboard` | `GET /dashboard` |
| **Hermes Agent Framework** | `:8642` | `/hermes/v1/*` | `GET /hermes/health` |
| **Jellyfin Media Server** | `:8096` | `/jellyfin/` | `GET /jellyfin/` |
| **Telegram Streamer** | Internal | `/tg-stream/` | `GET /tg-stream/health` |

---

## 📱 Client Integration Guides

### 1. Mobile Android APK / Custom Client Connection
Connect any OpenAI-compatible Android app or mobile UI to your personal Hermes agent:

- **Base URL**: `https://jishnupg-opencode-cli.hf.space/hermes/v1`
- **API Key**: `<your HERMES_GATEWAY_API_KEY secret>`
- **Models Endpoint**: `https://jishnupg-opencode-cli.hf.space/hermes/v1/models`
- **Chat Completions**: `https://jishnupg-opencode-cli.hf.space/hermes/v1/chat/completions`

### 2. Python OpenAI SDK
```python
from openai import OpenAI

# Connect to Hermes Agent
client = OpenAI(
    base_url="https://jishnupg-opencode-cli.hf.space/hermes/v1",
    api_key="your_hermes_secret_key",
)

response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Search the web for latest AI news"}],
)

print(response.choices[0].message.content)
```

### 3. Local CLI / Termux (`hermes setup`)
To run Hermes CLI on your own device using your Space's OmniRoute backend:
```bash
# Install Hermes CLI
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Run interactive setup
hermes setup
# Select Provider: OpenAI-compatible
# Base URL: https://jishnupg-opencode-cli.hf.space/v1
# API Key: key_oute_xxxxxxxxxxxx
```

---

## 🚀 Quick Start (Local Docker Run)

### Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose
- Environment file (`.env`)

### Running with Docker Compose
```bash
# Clone repository
git clone https://github.com/JishnuPG-tech/Project.git
cd Project

# Copy environment template
cp .env.example .env

# Build and launch container
docker compose up -d --build
```

Access the hub at `http://localhost:4096`.

---

## 🔐 Environment Variables & Secrets Reference

| Variable | Description | Required |
|---|---|---|
| `STORAGE_ENCRYPTION_KEY` | Master key for database field encryption | Yes |
| `OMNIROUTE_STORAGE_KEY` | Storage encryption key for OmniRoute SQLite | Yes |
| `JWT_SECRET` | Secret token for JWT session signing | Yes |
| `API_KEY_SECRET` | Secret key for OmniRoute API keys | Yes |
| `INITIAL_PASSWORD` | Initial admin password for web interfaces | Yes |
| `HERMES_MODEL` | Default model for Hermes Agent (default: `claude-sonnet-4-6`) | Optional |
| `TELEGRAM_BOT_TOKEN` | Bot token for Telegram integration | Optional |

---

## 📚 Documentation Reference

- 📄 [`HERMES_ARCHITECTURE.md`](HERMES_ARCHITECTURE.md) — Hermes Agent Framework architecture, port matrix, and locking rules.
- 🔒 [`OPENWEBUI_ARCHITECTURE.md`](OPENWEBUI_ARCHITECTURE.md) — Open WebUI architecture, assets resolution, and locking instructions.
- 🧠 [`OMNIROUTE_INTEGRATION_PLAN.md`](OMNIROUTE_INTEGRATION_PLAN.md) — OmniRoute AI Gateway routing architecture.
- 🚀 [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — Deployment and persistence guide.
- 🏗️ [`ARCHITECTURE.md`](ARCHITECTURE.md) — Multi-service system architecture overview.

---

## 📄 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for more information.
