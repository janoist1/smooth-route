from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.core.paths import data_path, image_path
import os
from pathlib import Path

app = FastAPI(
    title="Kátyúőr API",
    description="Backend for Smooth Route application",
    version="0.1.0"
)

from fastapi.middleware.cors import CORSMiddleware

# Local dev is permissive; the public read-only deploy restricts to the
# configured prod origin(s).
if settings.PUBLIC_READ_ONLY:
    _cors_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
else:
    _cors_origins = ["http://localhost:5173", "http://localhost:8000", "*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.routes import router as api_router
from app.core.migrations import ensure_database_schema

# Schema is owned by Alembic; pre-Alembic databases get stamped automatically.
if settings.RUN_MIGRATIONS_ON_STARTUP:
    ensure_database_schema()

# Include API router
app.include_router(api_router)

# GraphQL — AuthGraphQL resolves the caller identity into the context.
# Read-only deploy serves the query-only schema (no mutations reachable).
from app.graphql.context import AuthGraphQL
from app.graphql.schema import read_schema, schema
graphql_app = AuthGraphQL(read_schema if settings.PUBLIC_READ_ONLY else schema)
app.add_route("/graphql", graphql_app)
if not settings.PUBLIC_READ_ONLY:
    app.add_websocket_route("/graphql", graphql_app)

# Serve static files (web interface)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Serve generated previews from the canonical data directory. Skipped on the
# public read-only deploy: Vercel's serverless filesystem is read-only outside
# /tmp (this mkdir crashes the function at import), and the read-only API serves
# no locally generated previews anyway.
if not settings.PUBLIC_READ_ONLY:
    previews_dir = data_path("static", "previews")
    previews_dir.mkdir(parents=True, exist_ok=True)
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
    """Serve an image from the canonical data directory."""
    from fastapi import HTTPException

    try:
        path = image_path(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path.is_file():
        return FileResponse(path, media_type="image/jpeg")

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
