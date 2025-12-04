# Kátyúőr (smooth-route)

## Overview
Kátyúőr is an innovative route planning application that considers road quality to help users avoid potholes and poor road conditions.

## Project Structure
- `backend/`: FastAPI application handling route generation and image extraction.
- `docker-compose.yml`: Orchestrates the backend and PostGIS database.

## Setup

1.  **Prerequisites**:
    - Docker & Docker Compose
    - Google Maps API Key (Directions API & Street View Static API enabled)

2.  **Environment Variables**:
    Create a `.env` file in the root directory:
    ```bash
    GOOGLE_MAPS_API_KEY=your_api_key_here
    ```

3.  **Run the application**:
    
    **Option A: Docker (Recommended for easy setup)**
    ```bash
    docker-compose up --build
    ```

    **Option B: Local Development (venv)**
    ```bash
    # Create virtual environment
    python3 -m venv .venv
    source .venv/bin/activate
    
    # Install dependencies
    pip install -e backend/
    
    # Run DB (still need PostGIS)
    docker-compose up -d db
    
    # Run Backend
    uvicorn app.main:app --reload --app-dir backend
    ```

4.  **CLI Usage**:
    ```bash
    # Ensure .env is set up
    ./cli.sh generate-route "Start" "End"
    ./cli.sh list-routes
    ```

5.  **Access**:
    - API Documentation: http://localhost:8000/docs
