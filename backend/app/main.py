from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
import os
from pathlib import Path

app = FastAPI(
    title="Kátyúőr API",
    description="Backend for Smooth Route application",
    version="0.1.0"
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000", "*"], # Added * for dev flexibility, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.core.database import engine
from app.models.models import Base
from app.api.routes import router as api_router

# Create tables on startup
Base.metadata.create_all(bind=engine)

# Include API router
app.include_router(api_router)

# GraphQL
from strawberry.asgi import GraphQL
from app.graphql.schema import schema
graphql_app = GraphQL(schema)
app.add_route("/graphql", graphql_app)
app.add_websocket_route("/graphql", graphql_app)

# Serve static files (web interface)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Serve generated previews
backend_dir = os.path.dirname(os.path.dirname(__file__))
previews_dir = os.path.join(backend_dir, "data", "static", "previews")
if not os.path.exists(previews_dir):
    os.makedirs(previews_dir)
app.mount("/previews", StaticFiles(directory=previews_dir), name="previews")

@app.get("/")
async def root():
    return {
        "message": "Welcome to Kátyúőr API",
        "version": "0.1.0",
        "endpoints": {
            "api": "/api/v1/points",
            "web_map": "/map.html",
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

@app.get("/settings.html")
async def settings_page():
    """Serve the settings page."""
    settings_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "settings.html")
    if os.path.exists(settings_file):
        return FileResponse(settings_file)
    return {"error": "Settings page not found"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/images/{filename}")
async def get_image(filename: str):
    """Serve images from data directory (checking all locations)"""
    import os
    from fastapi import HTTPException
    
    # Check multiple possible locations to handle split datasets (legacy vs new)
    backend_app_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(backend_app_dir)
    project_root = os.path.dirname(backend_dir)
    
    candidates = [
        settings.resolve_data_dir(),          # 1. Configured preference
        os.path.join(project_root, "data"),   # 2. Legacy root data
        os.path.join(backend_dir, "data")     # 3. Backend local data
    ]
    
    for base_dir in candidates:
        image_path = os.path.join(base_dir, "images", filename)
        # Security check to ensure we stay within intended dirs could go here, 
        # but filename is simple string from URL usually basic. 
        # Adding basic traversal check:
        if ".." in filename or "/" in filename:
             continue
             
        if os.path.exists(image_path):
            return FileResponse(image_path, media_type="image/jpeg")
    
    raise HTTPException(status_code=404, detail="Image not found")

@app.get("/api/v1/exports/{filename}")
async def get_export_file(filename: str):
    """Serve exported files (notebooks, datasets) from the data/exports directory."""
    import os
    from fastapi import HTTPException
    
    data_dir = settings.resolve_data_dir()
    
    export_path = os.path.join(data_dir, "exports", filename)
    
    # Security: prevent directory traversal
    if not os.path.abspath(export_path).startswith(os.path.abspath(os.path.join(data_dir, "exports"))):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(export_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine media type based on extension
    if filename.endswith(".ipynb"):
        media_type = "application/x-ipynb+json"
    elif filename.endswith(".zip"):
        media_type = "application/zip"
    else:
        media_type = "application/octet-stream"
        
    return FileResponse(export_path, media_type=media_type, filename=filename)
