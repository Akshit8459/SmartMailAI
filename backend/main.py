import sys
import os

# Load .env before anything else reads environment variables
from dotenv import load_dotenv
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path)

# Ensure 'backend' directory is in PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.database import init_db
from app.api.router import api_router

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_STR)

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

# ── /        → landing.html (public SaaS landing page) ──────────────────────
@app.get("/", include_in_schema=False)
async def serve_landing():
    return FileResponse(os.path.join(frontend_dir, "landing.html"))

# ── /app     → index.html  (authenticated inbox shell) ──────────────────────
@app.get("/app", include_in_schema=False)
async def serve_app():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# ── /app/{path} → index.html (SPA fallback for deep-linking) ────────────────
@app.get("/app/{full_path:path}", include_in_schema=False)
async def serve_app_spa(full_path: str):
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# ── Serve all other static assets (CSS, JS, images, fonts) ──────────────────
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
