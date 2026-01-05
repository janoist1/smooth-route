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

@app.get("/api/v1/images/{filename}")
async def get_image(filename: str):
    """Serve images from the data/images directory."""
    import os
    from fastapi import HTTPException
    
    data_dir = settings.DATA_DIR
    if not os.path.isabs(data_dir):
        # __file__ is /backend/app/main.py
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        project_root = os.path.dirname(backend_dir)
        data_dir = os.path.join(project_root, data_dir)
    
    image_path = os.path.join(data_dir, "images", filename)
    
    # Security: prevent directory traversal
    if not os.path.abspath(image_path).startswith(os.path.abspath(os.path.join(data_dir, "images"))):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(image_path, media_type="image/jpeg")

@app.get("/api/v1/exports/{filename}")
async def get_export_file(filename: str):
    """Serve exported files (notebooks, datasets) from the data/exports directory."""
    import os
    from fastapi import HTTPException
    
    # __file__ is /backend/app/main.py, so parent is /backend/app, and its parent is /backend
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    
    data_dir = settings.DATA_DIR
    if not os.path.isabs(data_dir):
        data_dir = os.path.join(backend_dir, data_dir)
    
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
