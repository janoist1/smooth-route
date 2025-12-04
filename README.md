# Kátyúőr (smooth-route)

## Overview
Kátyúőr is an innovative route planning application that considers road quality to help users avoid potholes and poor road conditions.

**Architecture**: Point-based data storage. Routes are only used as tools to collect road points efficiently. All images and data are stored point-based (location + heading), not route-based.

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

4.  **CLI Usage** (Point-Based):
    ```bash
    # Collect points along a route (route is only a tool!)
    ./cli.sh collect-points "47.514700,19.040230" "47.513513,19.047038"
    
    # List all collected points
    ./cli.sh list-points
    
    # Download images for all points that have URLs but no local files yet
    ./cli.sh download-images
    
    # Limit number of downloads
    ./cli.sh download-images --limit 100
    
    # Analyze points
    ./cli.sh analyze-points --simple --save
    
    # Or using Docker
    ./cli.sh docker collect-points "Start" "End"
    ./cli.sh docker list-points
    ./cli.sh docker download-images
    
    # After installing: smooth-route command is available
    smooth-route --help
    ```
    
    **Note**: 
    - The CLI is available as `smooth-route` command after installation, or via `./cli.sh` wrapper script.
    - **Point-based architecture**: Routes are only tools to collect points. No routes are stored!

5.  **Data Storage** (Point-Based):
    - Images are stored **point-based**, NOT route-based
    - Structure: `data/images/{image_id}_{lat}_{lng}_{heading}.jpg`
    - Routes are only used as a tool to collect points efficiently
    - In Docker: automatically mounted and synchronized with host
    - Configurable via `DATA_DIR` environment variable
    - **Important**: No `route_X/` subdirectories - all images directly in `data/images/`

6.  **Access**:
    - CLI: `smooth-route --help` or `./cli.sh --help`
    - API: Currently CLI-only. API server runs but endpoints removed.
    - Health check: http://localhost:8000/health
