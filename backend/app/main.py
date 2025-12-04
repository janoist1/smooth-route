from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(
    title="Kátyúőr API",
    description="Backend for Smooth Route application (CLI-only for now)",
    version="0.1.0"
)

from app.core.database import engine, Base

# Create tables on startup
Base.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    return {
        "message": "Welcome to Kátyúőr API",
        "version": "0.1.0",
        "note": "Currently CLI-only. Use 'smooth-route --help' for commands."
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
