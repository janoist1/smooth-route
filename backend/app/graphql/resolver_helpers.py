"""Shared helpers for GraphQL resolvers."""
import os

from app.core.database import SessionLocal


def get_db_session():
    return SessionLocal()


def image_filename_from_url(url):
    """Extract the bare image filename from a stored image_url."""
    if not url:
        return None
    if url.startswith("images/"):
        return url.replace("images/", "")
    if "/data/images/" in url:
        return url.split("/data/images/")[-1]
    if url.startswith("http"):
        return url.split("/")[-1]
    return os.path.basename(url)
