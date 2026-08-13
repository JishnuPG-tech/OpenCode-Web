# Rule: Open WebUI Working Configuration Lock

Open WebUI is 100% verified, operational, and locked on Hugging Face Space.

## Rules to Enforce
1. **DO NOT MODIFY OPEN WEBUI ROUTING**:
   - `gateway/openwebui.py` must retain `@router.api_route("/_app/{path:path}")` proxying to `http://127.0.0.1:8098/_app/{sub_path}`.
   - Root-level WebSocket bindings `/ws/socket.io` must remain intact in `gateway/openwebui.py`.
2. **DO NOT MODIFY OPEN WEBUI ENVIRONMENT VARIABLES**:
   - `OPENAI_API_BASE_URL` in `entrypoint.sh` MUST remain `http://127.0.0.1:8000/v1` (to ensure guaranteed model list fallback).
   - `REDIS_URL` MUST remain UNSET (`unset REDIS_URL`) right before `open-webui serve` (to prevent Redis connection refused 111 auth errors).
3. **PRESERVE PERSISTENCE**:
   - The 120s backup loop for `/root/.open-webui/webui.db` -> `/data/open-webui/webui.db` MUST be preserved.
