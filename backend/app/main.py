from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.core.paths import data_path, image_path
import os
from pathlib import Path

# The public read-only deploy publishes no OpenAPI schema / Swagger UI: it
# serves only /graphql (+ /health), and the docs would advertise local-only
# REST endpoints.
_public = settings.PUBLIC_READ_ONLY
app = FastAPI(
    title="Kátyúőr API",
    description="Backend for Smooth Route application",
    version="0.1.0",
    docs_url=None if _public else "/docs",
    redoc_url=None if _public else "/redoc",
    openapi_url=None if _public else "/openapi.json",
)

from fastapi.middleware.cors import CORSMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

# Public read-only deploy: only the configured prod origin(s), no cookies
# (anonymous API; Apollo sends none cross-origin). Local dev: any localhost
# port (worktree dev servers), but not arbitrary websites — with "*" any page
# open in the developer's browser could drive the local admin API
# (AUTH_MODE=disabled makes every caller admin).
if _public:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# gzip: a zoom-13 roadSegments answer for Budapest is ~350 KB of JSON and
# compresses ~6x. Starlette skips text/event-stream, so the job SSE stream is
# untouched; bodies under 1 KB are sent as they are.
from starlette.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Added last = outermost: every response (incl. CORS preflights) gets them.
app.add_middleware(SecurityHeadersMiddleware)

from app.api.routes import router as api_router

# Schema is owned by Alembic; pre-Alembic databases get stamped automatically.
# Imported lazily inside the guard: the read-only deploy runs with
# RUN_MIGRATIONS_ON_STARTUP=false and ships without alembic (torch-free
# requirements.txt), so this import must not execute there.
if settings.RUN_MIGRATIONS_ON_STARTUP:
    from app.core.migrations import ensure_database_schema
    ensure_database_schema()

# Legacy REST API: local only. The public read-only deploy serves /graphql
# alone — GET /api/v1/points returned the whole table unbounded, and the
# image/export/job endpoints have nothing to serve there.
if not _public:
    app.include_router(api_router)

# GraphQL — AuthGraphQL resolves the caller identity into the context.
# Read-only deploy serves the query-only schema (no mutations reachable).
from app.graphql.context import AuthGraphQL
from app.graphql.schema import read_schema, schema
# Public: no GraphiQL page and POST only — a GET query can be fired from any
# <img>/<link> on any site, spreading paid getRoute calls over visitors' IPs.
graphql_app = (
    AuthGraphQL(read_schema, graphql_ide=None, allow_queries_via_get=False)
    if _public
    else AuthGraphQL(schema)
)
app.add_route("/graphql", graphql_app)
if not settings.PUBLIC_READ_ONLY:
    # Starlette 1.x dropped add_websocket_route; a WebSocketRoute works on both.
    from starlette.routing import WebSocketRoute
    app.router.routes.append(WebSocketRoute("/graphql", graphql_app))

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
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

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


# Local file servers (images, exports): not on the public read-only deploy.
if not _public:
    app.add_api_route("/images/{filename}", get_image, methods=["GET"])
    app.add_api_route("/api/v1/exports/{filename}", get_export_file, methods=["GET"])
