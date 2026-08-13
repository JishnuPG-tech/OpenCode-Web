# OpenCode Space — Production Deployment & Operations Manual

This guide provides step-by-step instructions for deploying, updating, scaling, and maintaining the **`Jishnupg/Opencode-Cli`** multi-service environment on Hugging Face Spaces or standard Docker / Kubernetes environments.

---

## 1. Prerequisites & Repository Remotes Setup

### Primary Repository Endpoints:
- **GitHub Source Repo**: `https://github.com/JishnuPG-tech/Project.git`
- **Hugging Face Space**: `https://huggingface.co/spaces/Jishnupg/Opencode-Cli`

### Git Remote Configuration:
To ensure updates are pushed cleanly to both GitHub and Hugging Face Space:

```bash
# Add Hugging Face Space remote
git remote add hf https://huggingface.co/spaces/Jishnupg/Opencode-Cli

# Verify remotes list
git remote -v
# Output should show:
# hf     https://huggingface.co/spaces/Jishnupg/Opencode-Cli (fetch)
# hf     https://huggingface.co/spaces/Jishnupg/Opencode-Cli (push)
# origin https://github.com/JishnuPG-tech/Project.git (fetch)
# origin https://github.com/JishnuPG-tech/Project.git (push)
```

---

## 2. Hugging Face Space Configuration & Secrets

In your Hugging Face Space settings (**Settings > Secrets**), configure the following environment secrets:

| Secret Key | Description | Example / Recommended Value |
| :--- | :--- | :--- |
| `STORAGE_ENCRYPTION_KEY` | Master AES-256-GCM key for encrypting provider credentials | 32-character random string |
| `JWT_SECRET` | Secret key for JWT token signing across services | 32-character random string |
| `API_KEY_SECRET` | Secret key for OmniRoute API key authorization | 32-character random string |
| `INITIAL_PASSWORD` | Default admin password for OmniRoute UI login | User-defined password |

> [!NOTE]
> If any secret is omitted during local Docker testing, `entrypoint.sh` automatically supplies safe default fallback values to prevent container crashes.

---

## 3. Build & Deployment Commands

### Standard Deployment Workflow:

```bash
# 1. Stage all modified code changes
git add .

# 2. Commit with conventional commit message
git commit -m "feat(omniroute): update gateway routing and provider persistence"

# 3. Push to GitHub repository
git push origin main

# 4. Push to Hugging Face Space repository (triggers automatic Docker build)
git push hf main
```

---

## 4. Local Testing with Docker

To build and run the entire multi-service container locally:

```bash
# Build the Docker image
docker build -t opencode-cli:latest .

# Run the container mapping public ingress port 4096
docker run -d \
  -p 4096:4096 \
  -e STORAGE_ENCRYPTION_KEY="my_secure_encryption_key_32bytes" \
  -e JWT_SECRET="my_secure_jwt_secret_key_32bytes" \
  -e API_KEY_SECRET="my_secure_api_key_secret_32bytes" \
  -e INITIAL_PASSWORD="admin_password_123" \
  --name opencode-space \
  opencode-cli:latest

# Check container logs
docker logs -f opencode-space
```

### Access Local Endpoints:
- **Unified Gateway**: `http://localhost:4096/`
- **OmniRoute Dashboard**: `http://localhost:4096/dashboard`
- **OpenAI API Base URL**: `http://localhost:4096/v1`
- **Jellyfin Media**: `http://localhost:4096/jellyfin`
- **TG Streamer**: `http://localhost:4096/tg-stream`

---

## 5. Maintenance & Troubleshooting

### Issue 1: `SyntaxError: Unexpected token '<'` in Frontend
- **Symptom**: Dashboard page shows "0 connections" or console logs `<JSON.parse error>`.
- **Cause**: Gateway routed an `/api/` request to Open WebUI instead of OmniRoute.
- **Fix**: Verify `gateway/main.py` has Referer-based routing enabled:
  ```python
  is_omniroute_referer = "/dashboard" in referer or "/omniroute" in referer or "/providers" in referer
  ```

### Issue 2: Duplicate Process Restarts (`FastAPI Gateway process died!`)
- **Symptom**: Container logs show repeated restart messages every 5s.
- **Cause**: Variable name mismatch between start command (`FASTAPI_PID=$!`) and supervisor check (`kill -0 $FASTAPI_PID`).
- **Fix**: Verify `FASTAPI_PID` is correctly set and checked in `entrypoint.sh`.

### Issue 3: Database Snapshot Restoration Check
- **Symptom**: Provider keys disappear after space rebuild.
- **Verification Command**:
  ```bash
  # Check if persistent volume snapshot exists
  ls -lh /data/omniroute/storage.sqlite
  
  # Manually trigger snapshot sync
  python3 -c "import sqlite3; conn = sqlite3.connect('/data/omniroute/storage.sqlite'); print(conn.execute('PRAGMA quick_check;').fetchall())"
  ```
