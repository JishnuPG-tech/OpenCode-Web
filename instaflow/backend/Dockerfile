# HuggingFace Spaces & Docker VPS Dockerfile for InstaFlow v2
FROM python:3.12-slim

# Install system dependencies (FFmpeg, Curl, Ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# HuggingFace Spaces runs containers with User ID 1000
RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONPATH=/home/user/app \
    PORT=7860 \
    TEMP_DIR=/tmp/instaflow_downloads \
    COOKIES_FILE=/home/user/app/cookies.txt

WORKDIR $HOME/app

# Copy requirements and install Python dependencies
COPY --chown=user:user requirements.txt $HOME/app/requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application files
COPY --chown=user:user . $HOME/app/backend
COPY --chown=user:user ../cookies.txt $HOME/app/cookies.txt

# Ensure temporary directory has write permissions
RUN mkdir -p /tmp/instaflow_downloads && chown -R user:user /tmp/instaflow_downloads $HOME

USER user

EXPOSE 7860

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
