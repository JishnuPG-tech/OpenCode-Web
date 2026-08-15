# OpenCode Space — System Architecture, Configuration & Troubleshooting Guide

This document serves as an exhaustive reference record for the fixes, configuration standards, and architectural design implemented for the OpenCode Space application stack.

---

## 📌 System Overview & Services

| Service | Local Endpoint | External Endpoint Path | Description |
|---|---|---|---|
| **Gateway Proxy** | `http://127.0.0.1:8000` | `https://jishnupg-opencode-cli.hf.space/` | FastAPI ASGI Reverse Proxy & Auto Model Resolver |
| **OmniRoute AI Gateway** | `http://127.0.0.1:20128` | `/v1/chat/completions` & `/dashboard` | Multi-provider AI router managing 105 connected models |
| **Hermes Agent** | `http://127.0.0.1:8642` | `/hermes/` | Autonomous AI agent backend & Telegram Bot integration |
| **Open WebUI** | `http://127.0.0.1:8098` | `/` (Root Web UI) | Web chat interface |
| **Telegram Streamer** | `http://127.0.0.1:8080` | `/tg_stream/` | Telegram file & media streaming service |
| **Jellyfin Media Server** | `http://127.0.0.1:8096` | `/jellyfin/` | Media server application |

---

## 🔑 Master Credentials & API Keys

- **OmniRoute Master API Key**: `sk-6646a5f2024f6318-d27ff7-f3e152c8`
- **Connected Providers**:
  - **Antigravity**: 3 Models (`antigravity/gemini-3.6-flash-medium`, `antigravity/claude-sonnet-4-6`, etc.)
  - **NVIDIA NIM**: 102 Free Models (`meta/llama-3.3-70b-instruct`, etc.)

---

## 🛠️ Critical Issues Fixed & Solutions Applied

### 1. Gateway Auto Model Resolver & Fallback Engine
- **Problem**: When Hermes Agent, Telegram Bot, or external clients requested model `"auto"` or `"auto/best-fast"`, OmniRoute's internal Next.js server attempted public free web scrapers (`grok-cli`, `gemini-web`, `opencode/mimo`). These public scrapers failed with **HTTP 429 Rate Limits** or **Playwright 500 Errors**, returning `503 Service Unavailable` and causing *"The model provider failed after retries"*.
- **Solution**:
  - Updated `gateway/omniroute.py` and `gateway/hermes_standalone.py` to intercept `"auto"` and `"auto/*"` requests.
  - Automatically fetches the live model catalog from `/v1/models`, filters out `auto/` and `omniroute/` scrapers, and extracts real connected provider models.
  - Sequentially tries active models (`antigravity/gemini-3.6-flash-medium`, `meta/llama-3.3-70b-instruct`) and returns `200 OK` on the first successful choice.

---

### 2. Telegram Bot API Base URL & Model Alignment
- **Problem**: Hermes Telegram Bot was pointing to `http://127.0.0.1:20128/v1` directly, bypassing the Gateway auto-resolver.
- **Solution**:
  - Updated `HERMES_API_BASE_URL` and `OPENAI_API_BASE` in `entrypoint.sh` to point to `http://127.0.0.1:8000/v1` (the Gateway auto-resolver).
  - Set default `HERMES_MODEL="antigravity/gemini-3.6-flash-medium"` in `entrypoint.sh` for instant, lag-free responses.

---

### 3. Open WebUI SQLite WAL Lock & Disk I/O Error
- **Problem**: Open WebUI crashed on startup with `sqlite3.OperationalError: disk I/O error` when executing `PRAGMA journal_mode=WAL` because SQLite WAL shared memory lock files (`.db-wal` / `.db-shm`) cannot lock across persistent volume container mounts.
- **Solution**:
  - Added WAL lock file purging (`rm -f *.db-wal *.db-shm`) in `entrypoint.sh`.
  - Added an automated python patch in `entrypoint.sh` that modifies `/usr/local/lib/python*/dist-packages/open_webui/internal/db.py` to replace `PRAGMA journal_mode=WAL` with `PRAGMA journal_mode=DELETE`.

---

### 4. OmniRoute Authentication & Transparent Errors
- **Problem**: `gateway/omniroute.py` was returning a fake `HTTP 200 OK {"authenticated": false}` JSON body on HTTP 401/403 responses.
- **Solution**:
  - Set `OMNIROUTE_ALLOW_UNAUTHENTICATED=true` in `entrypoint.sh` for local internal gateway proxy calls.
  - Restricted the fake unauthenticated JSON response in `gateway/omniroute.py` strictly to HTML dashboard paths, allowing API routes (`/v1/chat/completions`) to pass through raw status codes and choices transparently.

---

## 🧪 Verification & Testing Commands

### 1. Test via Python (`test.py`)
```python
import urllib.request
import json
import ssl

url = "https://jishnupg-opencode-cli.hf.space/v1/chat/completions"
headers = {
    "Authorization": "Bearer sk-6646a5f2024f6318-d27ff7-f3e152c8",
    "Content-Type": "application/json"
}

payload = {
    "model": "auto",
    "messages": [{"role": "user", "content": "Explain quantum computing in one short sentence."}]
}

ctx = ssl.create_default_context()
req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')

with urllib.request.urlopen(req, context=ctx) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    print("Status:", resp.status)
    print("Model Used:", data.get("model"))
    print("Answer:", data["choices"][0]["message"]["content"])
```

### 2. Test via cURL
```bash
curl -X POST "https://jishnupg-opencode-cli.hf.space/v1/chat/completions" \
  -H "Authorization: Bearer sk-6646a5f2024f6318-d27ff7-f3e152c8" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

---

## 📋 Rules for Future Development
> [!IMPORTANT]
> 1. **Do not set `HERMES_API_BASE_URL` directly to port 20128**. Always point to Gateway port `8000` (`http://127.0.0.1:8000/v1`) so the Gateway auto-resolver maps `"auto"` to real provider models.
> 2. **Never allow `PRAGMA journal_mode=WAL` in Open WebUI**. Persistent volumes on Hugging Face Spaces require `journal_mode=DELETE` to prevent SQLite disk I/O errors.
> 3. **Preserve Master Key default**: `sk-6646a5f2024f6318-d27ff7-f3e152c8` must remain synced across `entrypoint.sh`, `gateway/hermes_standalone.py`, `gateway/omniroute.py`, and `gateway/hermes.py`.
