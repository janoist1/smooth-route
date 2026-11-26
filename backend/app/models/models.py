import uuid

from sqlalchemy import BigInteger, CheckConstraint, Column, Date, Integer, String, Float, DateTime, JSON, UniqueConstraint, Uuid, func
from sqlalchemy.orm import declarative_base
from geoalchemy2 import Geometry

from app.core.timeutil import utcnow

Base = declarative_base()

ROLE_USER = "user"
ROLE_ADMIN = "admin"


class User(Base):
    """
    Application user, provisioned just-in-time from a verified Clerk JWT.
    Identity lives in Clerk; this row anchors role and future quota/job FKs.
    Roles: 'user' (default) or 'admin' (promoted manually via SQL).
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    clerk_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=True)
    role = Column(String, nullable=False, default=ROLE_USER, server_default=ROLE_USER)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class StreetViewImage(Base):
    """
    Point-based storage: Each image represents a unique road point.
    Defined by location (lat, lng) + heading (direction).

    Routes are NOT stored - they are only tools to collect points.
    When planning a route later, we query existing points.
    """

    __tablename__ = "street_view_images"

    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, index=True)
    longitude = Column(Float, index=True)
    heading = Column(Float, index=True)
    pitch = Column(Float)
    image_url = Column(String)  # Can be URL or local path
    # Street View panorama id (from the free metadata API). Lets the public
    # site deep-link to the exact panorama without storing/serving the image.
    pano_id = Column(String, nullable=True, index=True)
    # When Google captured that panorama (Metadata API `date`, month
    # precision → stored as the 1st of the month). NULL = unknown. The RQI is
    # only as current as this date, not as `created_at` (our download time).
    capture_date = Column(Date, nullable=True, index=True)
    location = Column(Geometry("POINT", srid=4326), index=True)
    created_at = Column(DateTime, default=utcnow)

    # AI Analysis results
    rqi_score = Column(Float, nullable=True, index=True)
    damage_count = Column(Integer, default=0)
    damage_types = Column(JSON, nullable=True)
    analysis_metadata = Column(
        JSON, nullable=True
    )  # Detailed analysis info (edge_density, variance, damage_score, etc.)
    # DINO Analysis
    dino_rqi_score = Column(Float, nullable=True, index=True)

class RoadSegment(Base):
    """
    A ~150 m piece of an OSM way with the quality aggregated from the Street
    View frames snapped onto it (see app/services/road_segments.py).

    Derived data: `backend/scripts/build_segments.py` rebuilds the table from
    street_view_images + cached OSM geometry, so it is safe to wipe.
    Geometry © OpenStreetMap contributors (ODbL).
    """

    __tablename__ = "road_segments"
    __table_args__ = (
        UniqueConstraint("osm_way_id", "piece_index", name="uq_road_segments_way_piece"),
    )

    # "<osm_way_id>:<piece_index>" — stable across rebuilds, so client caches
    # keyed by id stay valid.
    id = Column(String, primary_key=True)
    osm_way_id = Column(BigInteger, nullable=False, index=True)
    piece_index = Column(Integer, nullable=False)
    geom = Column(Geometry("LINESTRING", srid=4326), nullable=False)
    length_m = Column(Float, nullable=False)
    road_name = Column(String, nullable=True)
    highway = Column(String, nullable=True)  # OSM highway class
    # Aggregates; score/rqi/p_bad are NULL for a piece without frames.
    n_images = Column(Integer, nullable=False, default=0, server_default="0")
    score = Column(Float, nullable=True)  # aggregated continuous score, canonical RQI scale
    rqi = Column(Integer, nullable=True)  # canonical RQI level (shared/rqi_scale.json)
    p_bad = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0, server_default="0")
    capture_date_min = Column(Date, nullable=True)
    capture_date_max = Column(Date, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, server_default=func.now())


class Job(Base):
    """
    Background job tracking.
    """
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True)
    status = Column(String, default="pending")
    current_step = Column(String, nullable=True)
    progress = Column(Integer, default=0)
    total = Column(Integer, default=0)
    message = Column(String, default="")
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)



class TrainingData(Base):
    """
    Stores manual training data for Machine Learning.
    Includes ground truth RQI, bounding boxes, tags, and metadata.
    """

    __tablename__ = "training_data"

    id = Column(Integer, primary_key=True, index=True)
    image_filename = Column(String, unique=True, index=True)  # Link to file on disk
    manual_rqi = Column(Float, nullable=True)  # Human ground truth on the canonical RQI scale (shared/rqi_scale.json)
    
    # Annotations: List of {id, label, x, y, w, h} OR {id, label, points: [[x,y], ...]} for polygons
    annotations = Column(JSON, default=[]) 
    
    # Internal metrics (calculated from area %)
    rqi_area_percent = Column(Float, default=0.0)
    
    # Tags: List of strings e.g. ["shadow", "wet", "occlusion"]
    tags = Column(JSON, default=[])

    # Optional user comment
    comment = Column(String, nullable=True)
    
    # Flexible metadata bucket
    meta_data = Column(JSON, default={})
    
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
