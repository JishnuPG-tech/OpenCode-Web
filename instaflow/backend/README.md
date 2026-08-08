# ⚡ InstaFlow v2 Remote Processing Engine (FastAPI)

Production-ready, lightweight, stateless FastAPI backend server for Instagram Reels, Posts, Carousels, and Media streaming. 

Designed for **Docker**, **HuggingFace Spaces**, **VPS (DigitalOcean / AWS / Hetzner)**, **Railway**, **Render**, and **Kubernetes**.

---

## 🚀 Quickstart

### 1. Local Run
```bash
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

### 2. Docker Run
```bash
docker build -t instaflow-backend -f Dockerfile .
docker run -d -p 8000:7860 instaflow-backend
```

---

## 📡 API Endpoints

- `GET /health`: Health check and system status
- `POST /api/v1/analyze`: Returns structured metadata (Single Photo, Video Reel, Carousel)
- `POST /api/v1/download`: Downloads and streams media file directly in 128KB chunks
- `GET /api/v1/download?url=...&item=1`: GET download streaming endpoint for mobile clients

---

## 🔐 Instagram Login Cookie Setup
Place your valid `cookies.txt` file in the root project directory or pass session cookies dynamically via the API.
