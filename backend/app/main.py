from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(
    title="Kátyúőr API",
    description="Backend for Smooth Route application",
    version="0.1.0"
)

from app.api.routes import router as api_router
from app.core.database import engine, Base

# Create tables on startup
Base.metadata.create_all(bind=engine)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to Kátyúőr API", "version": "0.1.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
