from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
import os

app = FastAPI(
    title="Kátyúőr API",
    description="Backend for Smooth Route application",
    version="0.1.0"
)

from app.core.database import engine
from app.models.models import Base
from app.api.routes import router as api_router

# Create tables on startup
Base.metadata.create_all(bind=engine)

# Include API router
app.include_router(api_router)

# Serve static files (web interface)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return {
        "message": "Welcome to Kátyúőr API",
        "version": "0.1.0",
        "endpoints": {
            "api": "/api/v1/points",
            "web": "/map.html",
            "docs": "/docs"
        }
    }

@app.get("/map.html")
async def map_page():
    """Serve the map visualization page."""
    map_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "map.html")
    if os.path.exists(map_file):
        return FileResponse(map_file)
    return {"error": "Map page not found"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
