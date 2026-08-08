import uuid
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings
from backend.app.core.logging import request_id_ctx_var, logger
from backend.app.api.health import router as health_router
from backend.app.api.analyze import router as analyze_router
from backend.app.api.download import router as download_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS Middleware for full client accessibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware for correlation Request IDs
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_ctx_var.set(req_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    request_id_ctx_var.reset(token)
    return response

# Include API Routers
app.include_router(health_router, tags=["Health"])
app.include_router(analyze_router, prefix=settings.API_V1_PREFIX, tags=["Analyze"])
app.include_router(download_router, prefix=settings.API_V1_PREFIX, tags=["Download"])

@app.on_event("startup")
def startup_event():
    logger.info(f"InstaFlow Remote Processing Engine started on {settings.HOST}:{settings.PORT}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
