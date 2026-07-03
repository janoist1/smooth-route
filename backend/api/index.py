"""Vercel Python entrypoint for the round-1 read-only API (api.simaut.hu).

Serves the SAME FastAPI app as local dev — the read-only behaviour comes from
env, not a code fork. Set on the Vercel project:
    PUBLIC_READ_ONLY=1
    RUN_MIGRATIONS_ON_STARTUP=false   (Neon schema is managed via publish/migrate)
    DATABASE_URL=<neon connection string>
    GOOGLE_MAPS_API_KEY=<key>          (for the getRoute Directions proxy)
    ALLOWED_ORIGINS=https://simaut.hu
"""
import os
import sys

# Make the `app` package importable when Vercel runs this file from api/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402  (ASGI app; @vercel/python serves it)
