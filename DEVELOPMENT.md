# Smooth Route (Kátyúőr) - Development Documentation

## Project Overview

**Project Name**: Kátyúőr (Codename: smooth-route)  
**Purpose**: An innovative route planning application that considers road surface quality to help users avoid potholes and poor road conditions, protecting their vehicles.

**Core Philosophy**: 
- **Point-based data architecture**: We don't think in routes, but in **points** (location + heading). Routes are constructed by querying these points.
- **Deduplication strategy**: Avoid duplicate image downloads by reusing existing road points within configurable thresholds (distance + heading tolerance).
- **Route as tool**: Routes are only used as a tool to collect points efficiently (A→B path). Data storage is always point-based, never route-based.

---

## Architecture Overview

### Data Model Philosophy

The system uses a **point-centric** approach rather than route-centric:

1. **Road Points** (`StreetViewImage`) are stored as unique entities defined by:
   - Location (latitude, longitude)
   - Heading (direction of travel)
   - Associated image and analysis data

2. **Routes** are NOT stored - they are only tools used during point collection (A→B path). When planning routes later, we query existing points.

3. **Deduplication** happens at point creation time:
   - Before creating a new `StreetViewImage`, check if one exists within:
     - Distance threshold: `DEDUPLICATION_RADIUS_METERS` (default: 10m)
     - Heading tolerance: `DEDUPLICATION_HEADING_TOLERANCE` (default: 30°)
   - If found, reuse the existing point instead of creating a new one.

### Database Schema

**Point-Based Architecture**: Only points are stored, NO routes!

```
StreetViewImage (street_view_images) - The ONLY table!
├── id (primary key)
├── latitude, longitude (indexed)
├── heading (indexed)
├── pitch
├── location (POINT geometry, PostGIS, indexed)
├── image_url (URL or local path)
├── rqi_score (1-5, nullable, indexed)
├── damage_count
├── damage_types (JSON)
└── created_at
```

**Key Points**:
- ✅ **NO Route table** - Routes are only tools to collect points
- ✅ **NO RoutePoint table** - No route associations
- ✅ **Point-based storage** - Each point is unique (location + heading)
- ✅ **Deduplication** - Points are reused if within threshold (distance + heading)
- ✅ **Route planning later** - Query existing points when planning routes

---

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **ORM**: SQLAlchemy 2.0+
- **Database**: PostgreSQL with PostGIS extension
- **Spatial Queries**: GeoAlchemy2 for PostGIS integration
- **CLI**: Typer with Rich for beautiful terminal output

### External Services
- **Google Maps APIs**:
  - Directions API (route generation)
  - Street View Static API (image retrieval)

### AI/ML
- **Computer Vision**: 
  - YOLOv8 (Ultralytics) for damage detection
  - OpenCV for image processing
  - Fallback: Simple heuristic analysis (no ML required)

### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Database**: PostGIS 16-3.4 (via Docker)

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Google Maps API
GOOGLE_MAPS_API_KEY=your_api_key_here

# Database (defaults shown)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/smooth_route

# Quota Management
DAILY_IMAGE_QUOTA=1000  # Conservative default to stay within free tier

# Deduplication Settings
DEDUPLICATION_RADIUS_METERS=10.0      # Distance threshold in meters
DEDUPLICATION_HEADING_TOLERANCE=30.0  # Heading tolerance in degrees

# Data Directory (optional, defaults to "data")
DATA_DIR=data  # Relative to project root or absolute path
```

### Configuration File

Settings are managed via `backend/app/core/config.py` using Pydantic Settings.

---

## Development Workflow

### Setup

1. **Prerequisites**:
   ```bash
   # Docker & Docker Compose
   docker --version
   docker-compose --version
   
   # Python 3.11+ (for local development)
   python3 --version
   ```

2. **Environment Setup**:
   ```bash
   # Create .env file
   cp .env.example .env  # If exists, or create manually
   # Edit .env and add GOOGLE_MAPS_API_KEY
   ```

3. **Start Services**:
   ```bash
   # Start database
   docker-compose up -d db
   
   # Or start everything
   docker-compose up --build
   ```

4. **Initialize Database**:
   ```bash
   # Using CLI
   python -m app.cli init-db
   
   # Or via Docker
   docker-compose exec backend python -m app.cli init-db
   ```

### Local Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e backend/

# Run database (Docker)
docker-compose up -d db

# Run backend (local)
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## CLI Commands

The CLI is accessible via:
- **Installed command**: `smooth-route` (after `pip install -e backend/`)
- **Module**: `python -m app.cli`
- **Wrapper script**: `./cli.sh` (supports both local and Docker)

### Running CLI

**Local (with venv)**:
```bash
# Setup venv (first time)
python3 -m venv .venv
source .venv/bin/activate
pip install -e backend/

# Run commands
./cli.sh list-points
# or
smooth-route list-points
```

**Docker**:
```bash
./cli.sh docker list-points
# or
docker-compose run --rm backend smooth-route list-points
```

### Database Management

```bash
# Initialize database tables
smooth-route init-db
# or
./cli.sh init-db
```

### Point Collection

```bash
# Collect points along a route (route is only a tool!)
smooth-route collect-points "Budapest, Deák Ferenc tér" "Budapest, Széll Kálmán tér"
# or with coordinates
smooth-route collect-points "47.514700,19.040230" "47.513513,19.047038"

# List all collected points
smooth-route list-points
```

### Image Management

```bash
# Download Street View images for all points that have URLs but no local files yet
smooth-route download-images

# Limit number of downloads
smooth-route download-images --limit 100

# Custom output directory (still point-based)
smooth-route download-images --output-dir /path/to/custom/dir

# Images stored as: data/images/{image_id}_{lat}_{lng}_{heading}.jpg
```

**Note**: The `download-images` command automatically downloads images for all points created by `collect-points` that have URLs but haven't been downloaded yet. No need to specify coordinates or radius - it simply processes all pending downloads.

### Road Quality Analysis

```bash
# Analyze a single image (point-based path)
smooth-route analyze-image data/images/00001_47.514730_19.040210_267.jpg

# Analyze with simple heuristic (no YOLO)
smooth-route analyze-image data/images/00001_47.514730_19.040210_267.jpg --simple

# Analyze all points with downloaded images
smooth-route analyze-points --simple --save

# Analyze points in a specific area
smooth-route analyze-points --lat 47.5 --lng 19.0 --radius 500 --simple --save

# Options:
#   --lat, --lng: Center point for area analysis (optional)
#   --radius: Radius in meters (default: 1000m)
#   --limit N: Analyze first N points (0 = all)
#   --simple: Use heuristic analysis instead of YOLO
#   --save/--no-save: Save RQI scores to database
```

---

## API Endpoints

### Base URL
- Local: `http://localhost:8000`
- Docs: `http://localhost:8000/docs` (Swagger UI)

### Endpoints

**Note**: Currently CLI-only. API endpoints removed for now.

The FastAPI server runs but only provides:
- `GET /` - Basic info
- `GET /health` - Health check

All functionality is available via CLI commands (see CLI Commands section).

---

## Core Services

### GoogleMapsService (`backend/app/services/google_maps.py`)

**Key Methods**:
- `get_route(origin, destination)`: Get route polyline from Directions API
- `decode_polyline(polyline_str)`: Decode polyline to lat/lng points
- `interpolate_points(points, interval_meters)`: Create dense point cloud (~10m spacing)
- `calculate_heading(p1, p2)`: Calculate bearing between two points
- `generate_street_view_metadata(points)`: Generate image metadata with headings

**Usage**:
```python
from app.services.google_maps import google_maps_service

polyline = google_maps_service.get_route("A", "B")
points = google_maps_service.decode_polyline(polyline)
dense = google_maps_service.interpolate_points(points, interval_meters=10.0)
metadata = google_maps_service.generate_street_view_metadata(dense)
```

### RoadQualityService (`backend/app/services/road_quality.py`)

**Key Methods**:
- `analyze_image(image_path)`: Full YOLO-based analysis
- `analyze_image_simple(image_path)`: Heuristic-based analysis (no ML)

**Road Quality Index (RQI)**:
- **1**: Excellent (no damage)
- **2**: Good (minor issues)
- **3**: Fair (moderate damage)
- **4**: Poor (significant damage)
- **5**: Very Poor (severe damage)

**Damage Types** (RDD2020 standard):
- `D00`: Longitudinal Crack
- `D10`: Transverse Crack
- `D20`: Alligator Crack
- `D40`: Pothole

**Usage**:
```python
from app.services.road_quality import road_quality_service

result = road_quality_service.analyze_image("path/to/image.jpg")
print(f"RQI: {result.rqi_score}, Damages: {result.damage_count}")
```

---

## Deduplication Logic

### How It Works

When generating a route:

1. **For each point** in the interpolated route:
   - Calculate location (lat, lng) and heading
   - Query database for existing `StreetViewImage` where:
     ```sql
     ST_DistanceSphere(location, new_point) < DEDUPLICATION_RADIUS_METERS
     AND ABS(heading - new_heading) < DEDUPLICATION_HEADING_TOLERANCE
     ```
   - If found: Reuse existing image ID
   - If not found: Create new `StreetViewImage` entry

2. **Link to route** via `RoutePoint` association table

### Benefits

- **Cost savings**: Avoid duplicate API calls for overlapping routes
- **Storage efficiency**: One image can serve multiple routes
- **Data consistency**: Same location always has same RQI score

### Configuration

Adjust thresholds in `.env`:
```bash
DEDUPLICATION_RADIUS_METERS=10.0      # Increase for more aggressive deduplication
DEDUPLICATION_HEADING_TOLERANCE=30.0  # Increase to allow wider heading variance
```

**Trade-offs**:
- Larger radius = more reuse, but potentially less accurate for specific routes
- Smaller radius = more precise, but more duplicate images

---

## Project Phases

### ✅ Phase 1: Image Extraction Between Two Points
**Status**: Complete

- Google Maps API integration
- Route generation with Directions API
- Dense point interpolation (~10m spacing)
- Street View image metadata generation
- Database storage with PostGIS

### ✅ Phase 2: Point-Based Architecture
**Status**: Complete

- Removed Route and RoutePoint tables completely
- Pure point-based storage (StreetViewImage only)
- Spatial deduplication logic (distance + heading)
- CLI implementation with point-based commands
- Routes are only tools, not stored

### 🔄 Phase 2.5: Road Quality Analysis
**Status**: In Progress

- YOLO-based damage detection
- Simple heuristic fallback
- RQI score calculation (1-5 scale)
- Database integration for RQI storage

### ✅ Phase 3: API Cleanup
**Status**: Complete

- Removed API endpoints (CLI-only for now)
- Simplified main.py

### 📋 Phase 4: Frontend/Mobile App (MVP)
**Status**: Planned

- Android/iOS application
- Google Maps SDK integration
- Heatmap visualization (RQI color coding)
- Route planning with quality consideration

### 📋 Phase 5: Advanced Features
**Status**: Future

- Crowdsourcing (accelerometer data)
- Manual pothole reporting
- Real-time notifications
- Community-driven updates

---

## Testing Strategy

### Manual Testing

1. **Deduplication Test**:
   ```bash
   # Collect points along Route A
   smooth-route collect-points "Point A" "Point B"
   
   # Collect points along Route B that overlaps Route A
   smooth-route collect-points "Point A" "Point C"  # Overlaps with Route A
   
   # Verify: Check database - overlapping points should be reused
   smooth-route list-points
   ```

2. **Image Analysis Test**:
   ```bash
   # Download images
   smooth-route download-images
   
   # Analyze with simple method
   smooth-route analyze-points --simple --save
   
   # Verify: Check database for RQI scores
   smooth-route list-points
   ```

### Automated Tests

Location: `backend/tests/`

**TODO**: Implement comprehensive test suite:
- Unit tests for services
- Integration tests for API endpoints
- Spatial query tests for deduplication
- Image analysis accuracy tests

---

## Database Queries

### Useful Queries

```sql
-- Count images per route
SELECT r.id, r.origin, r.destination, COUNT(rp.id) as point_count
FROM routes r
LEFT JOIN route_points rp ON r.id = rp.route_id
GROUP BY r.id;

-- Find duplicate images (shared across routes)
SELECT si.id, si.latitude, si.longitude, COUNT(DISTINCT rp.route_id) as route_count
FROM street_view_images si
JOIN route_points rp ON si.id = rp.image_id
GROUP BY si.id
HAVING COUNT(DISTINCT rp.route_id) > 1;

-- Average RQI per route
SELECT r.id, AVG(si.rqi_score) as avg_rqi
FROM routes r
JOIN route_points rp ON r.id = rp.route_id
JOIN street_view_images si ON rp.image_id = si.id
WHERE si.rqi_score IS NOT NULL
GROUP BY r.id;

-- Find images within radius of a point (spatial query)
SELECT id, latitude, longitude, heading
FROM street_view_images
WHERE ST_DistanceSphere(
    location,
    ST_GeomFromText('POINT(19.040235 47.497912)', 4326)
) < 10.0;
```

---

## Known Issues & TODOs

### Current Issues

1. **Image Download Path Handling**:
   - `download-images` updates `image_url` to local path
   - Should use separate `image_path` field or handle URLs better

2. **Quota Management**:
   - Basic daily quota check exists but not comprehensive
   - Should track API calls, not just DB entries

3. **Route Planning**:
   - Need to implement route planning that queries existing points
   - Should find points along a planned path and calculate route quality

### Planned Improvements

1. **Batch Processing**:
   - Add batch image analysis endpoint
   - Background job processing for large routes

2. **Model Training**:
   - Fine-tune YOLO model on RDD2020 dataset
   - Improve damage detection accuracy

3. **Caching**:
   - Cache route calculations
   - Cache image analysis results

4. **Monitoring**:
   - Add logging and metrics
   - API usage tracking dashboard

---

## Data Storage

### Data Directory - Point-Based Structure

**IMPORTANT**: All data is stored **point-based**, NOT route-based!

All application data (downloaded images, etc.) is stored in the `data/` directory by default:
- **Local development**: `./data/` (relative to project root)
- **Docker**: `/app/data/` (mapped to `./data/` via volume)

The data directory structure is **point-based**:
```
data/
└── images/
    ├── 00001_47.514730_19.040210_267.jpg  # {image_id}_{lat}_{lng}_{heading}.jpg
    ├── 00002_47.514724_19.039979_267.jpg
    ├── 00003_47.514719_19.039747_267.jpg
    └── ...
```

**Key Points**:
- ❌ **NO** `route_X/` subdirectories
- ✅ Images stored directly in `data/images/` with unique identifiers
- ✅ Filename format: `{image_id}_{latitude}_{longitude}_{heading}.jpg`
- ✅ Routes are only used as a tool to collect points, not for storage organization

### Docker Volume Mapping

The `data/` directory is automatically mounted as a volume in Docker:
- **Host**: `./data/` (project root)
- **Container**: `/app/data/`
- **Synchronization**: Changes are immediately visible on both sides

This means:
- ✅ Images downloaded in Docker are accessible locally
- ✅ Images downloaded locally are accessible in Docker
- ✅ Data persists even when containers are removed
- ✅ Point-based structure works identically in both environments

### Configuration

You can customize the data directory via environment variable:
```bash
# In .env file
DATA_DIR=/custom/path/to/data
```

Or override per command:
```bash
smooth-route download-images --limit 100 --output-dir /custom/path
```

## File Structure

```
smooth-route/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── cli.py                # CLI commands (Typer)
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routes.py        # API endpoints
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py        # Settings (Pydantic)
│   │   │   └── database.py      # SQLAlchemy setup
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── models.py        # SQLAlchemy models
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── google_maps.py   # Google Maps API service
│   │       └── road_quality.py  # AI/ML analysis service
│   ├── tests/
│   │   └── test_api.py
│   ├── Dockerfile
│   ├── pyproject.toml           # Dependencies + CLI entry point
│   └── README.md
├── data/                         # Data directory (mounted in Docker)
│   └── images/                  # Downloaded Street View images (point-based)
│       ├── 00001_47.514730_19.040210_267.jpg
│       ├── 00002_47.514724_19.039979_267.jpg
│       └── ...                  # All images directly here, NO route subdirectories
├── docker-compose.yml           # Docker orchestration + volume mapping
├── cli.sh                        # CLI wrapper script (local/Docker)
├── README.md                     # User-facing README
└── DEVELOPMENT.md               # This file
```

---

## Git Workflow

### Commit Strategy

Commit after each logical block completion:
- ✅ Database schema changes
- ✅ Service implementation
- ✅ CLI command addition
- ✅ API endpoint addition
- ✅ Bug fixes
- ✅ Configuration updates

### Branch Strategy

- `master`: Stable, production-ready code
- `develop`: Integration branch for features
- `feature/*`: Feature branches
- `fix/*`: Bug fix branches

---

## Resources & References

### Documentation
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [PostGIS Documentation](https://postgis.net/documentation/)
- [Google Maps APIs](https://developers.google.com/maps/documentation)
- [YOLOv8 Documentation](https://docs.ultralytics.com/)

### Datasets
- [RDD2020 - Road Damage Dataset](https://github.com/sekilab/RoadDamageDetector)

### Related Projects
- Similar concepts: Waze (crowdsourcing), Google Maps (route planning)

---

## Contact & Support

For development questions or issues, refer to:
- Project repository: [GitHub URL]
- Issue tracker: [GitHub Issues]

---

**Last Updated**: 2024
**Maintainer**: Development Team

