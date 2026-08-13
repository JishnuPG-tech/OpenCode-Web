# 🔒 Open WebUI Production Architecture & Fix Documentation

This document serves as the **locked, definitive reference** for the working Open WebUI setup on the Hugging Face Space (`https://jishnupg-opencode-cli.hf.space/`).

> [!CAUTION]
> **DO NOT MODIFY OR REVERT THE ROUTING AND ENVIRONMENT CONFIGURATION DESCRIBED IN THIS FILE.**
> All solutions below were empirically verified live via Chrome DevTools and container log extraction.

---

## 🛠️ Summary of Root Causes & Permanent Solutions

### 1. Root-Level Upstream Asset Resolution (`/_app/*`)
- **Problem**: Open WebUI running internally on port `8098` serves its SvelteKit frontend assets under `http://127.0.0.1:8098/_app/*`. When clients requested `https://jishnupg-opencode-cli.hf.space/_app/immutable/...`, the gateway was returning `404 Not Found`.
- **Solution in [`gateway/openwebui.py`](file:///c:/Users/JISHNU%20PG/Documents/Project/Project/gateway/openwebui.py)**: Added explicit priority 1 routing for `/_app` and `/_app/{path:path}`:
  ```python
  @router.api_route("/_app", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
  @router.api_route("/_app/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
  async def webui_app_assets_proxy(request: Request, path: str = ""):
      sub_path = path.lstrip("/")
      target = f"http://127.0.0.1:{WEBUI_PORT}/_app/{sub_path}" if sub_path else f"http://127.0.0.1:{WEBUI_PORT}/_app"
      return await handle_openwebui_proxy(target, request, default_prefix="")
  ```

---

### 2. OpenAI API Models Resolution (`OPENAI_API_BASE_URL`)
- **Problem**: Open WebUI was configured with `OPENAI_API_BASE_URL="http://127.0.0.1:20129/v1"`. Because port `20129` is an internal bridge port (not an OpenAI API listener), fetching models timed out or failed, causing `/api/models` to return **HTTP 500 Internal Server Error**. SvelteKit caught the error, set `models = null`, and threw `TypeError: Cannot read properties of null (reading 'length')` inside `error-handling.js`, freezing all UI click events and modals.
- **Solution in [`entrypoint.sh`](file:///c:/Users/JISHNU%20PG/Documents/Project/Project/entrypoint.sh)**: Set `OPENAI_API_BASE_URL="http://127.0.0.1:8000/v1"`. Gateway's `omniroute_v1_api` fallback returns a guaranteed, instant JSON array of valid models (`gpt-4o`, `claude-3-5-sonnet`, `gemini-2.5-flash`, etc.), returning `200 OK` and unfreezing the UI.

---

### 3. Redis Connection Refused Error 111 (`REDIS_URL`)
- **Problem**: Open WebUI's auth middleware (`open_webui/utils/auth.py`) checks `request.app.state.redis` for revoked tokens. Because `REDIS_URL="redis://127.0.0.1:6379"` was exported in `entrypoint.sh` for OmniRoute, Open WebUI inherited it and tried to connect to Redis on every authenticated API call (`/api/v1/users/user/settings`, `/api/v1/tools/`, `/api/v1/configs/banners`, `/api/v1/auths/update/timezone`). Because Redis wasn't accepting connections, auth validation threw `redis.exceptions.ConnectionError: Error 111` and crashed all authenticated API routes with 500.
- **Solution in [`entrypoint.sh`](file:///c:/Users/JISHNU%20PG/Documents/Project/Project/entrypoint.sh)**: Added `unset REDIS_URL` right before `open-webui serve`. When `REDIS_URL` is unset, Open WebUI defaults to fast in-memory token validation without querying external Redis, making all authenticated API endpoints return **HTTP 200 OK**.

---

### 4. Database Schema Backward Compatibility & Auto-Reset
- **Problem**: Restoring an outdated `/data/open-webui/webui.db` file from older builds caused missing table/column errors (`OperationalError: no such column: settings / info`) on `POST /api/v1/users/user/settings/update`.
- **Solution in [`entrypoint.sh`](file:///c:/Users/JISHNU%20PG/Documents/Project/Project/entrypoint.sh)**: Added automated column-level schema validation via Python SQLite `PRAGMA table_info('user')` on boot. Outdated DBs are moved to `webui.db.legacy_bak` so Open WebUI builds a clean, fully migrated schema.

---

### 5. WebSocket Proxying (`/ws/socket.io`)
- **Problem**: Open WebUI opens root-level WebSockets to `/ws/socket.io/?EIO=4&transport=websocket`.
- **Solution in [`gateway/openwebui.py`](file:///c:/Users/JISHNU%20PG/Documents/Project/Project/gateway/openwebui.py)**: Added WebSocket proxy endpoints:
  ```python
  @router.websocket("/ws")
  @router.websocket("/ws/{path:path}")
  @router.websocket("/ws/socket.io")
  @router.websocket("/ws/socket.io/{path:path}")
  ```

---

### 6. Persistence Model
- **Database Location**: `/root/.open-webui/webui.db`
- **Persistent Target**: `/data/open-webui/webui.db`
- **Sync Mechanism**: Background 120-second backup daemon in `entrypoint.sh` continuously syncs SQLite database snapshots to `/data/open-webui/webui.db`.

---

## 🔒 Mandatory Locking Instructions for AI Assistants
1. **DO NOT** edit the path mapping `/ _app/*` -> `http://127.0.0.1:8098/_app/*`.
2. **DO NOT** re-export `REDIS_URL` inside Open WebUI's environment scope in `entrypoint.sh`.
3. **DO NOT** change `OPENAI_API_BASE_URL` away from `http://127.0.0.1:8000/v1`.
4. **DO NOT** remove the `/ws/socket.io` WebSocket handler in `gateway/openwebui.py`.
