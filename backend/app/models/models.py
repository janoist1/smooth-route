import datetime as dt
import uuid
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, Integer, String, Float, DateTime, JSON, UniqueConstraint, Uuid, false, func
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from geoalchemy2 import Geometry, WKTElement

from app.core.timeutil import utcnow

Base = declarative_base()

ROLE_USER = "user"
ROLE_ADMIN = "admin"


def street_view_location(latitude: Optional[float], longitude: Optional[float]) -> Optional[WKTElement]:
    """Build the SRID 4326 point in longitude/latitude order, if both are known."""
    if latitude is None or longitude is None:
        return None
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def _default_street_view_location(context: Any) -> Optional[WKTElement]:
    # Covers ORM and Core inserts that omit location, including bulk publishing.
    values = context.get_current_parameters()
    return street_view_location(values.get("latitude"), values.get("longitude"))


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

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    clerk_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default=ROLE_USER, server_default=ROLE_USER)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class StreetViewImage(Base):
    """
    Point-based storage: Each image represents a unique road point.
    Defined by location (lat, lng) + heading (direction).

    Routes are NOT stored - they are only tools to collect points.
    When planning a route later, we query existing points.
    """

    __tablename__ = "street_view_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, index=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, index=True)
    heading: Mapped[Optional[float]] = mapped_column(Float, index=True)
    pitch: Mapped[Optional[float]] = mapped_column(Float)
    image_url: Mapped[Optional[str]] = mapped_column(String)  # Can be URL or local path
    # Street View panorama id (from the free metadata API). Lets the public
    # site deep-link to the exact panorama without storing/serving the image.
    pano_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    # When Google captured that panorama (Metadata API `date`, month
    # precision → stored as the 1st of the month). NULL = unknown. The RQI is
    # only as current as this date, not as `created_at` (our download time).
    capture_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True, index=True)
    location: Mapped[Optional[Any]] = mapped_column(
        Geometry("POINT", srid=4326), index=True, default=_default_street_view_location,
    )
    created_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, default=utcnow)

    # AI Analysis results
    rqi_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    damage_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    damage_types: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    analysis_metadata: Mapped[Optional[Any]] = mapped_column(
        JSON, nullable=True
    )  # Detailed analysis info (edge_density, variance, damage_score, etc.)
    # DINO Analysis
    dino_rqi_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)

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
    id: Mapped[str] = mapped_column(String, primary_key=True)
    osm_way_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    piece_index: Mapped[int] = mapped_column(Integer, nullable=False)
    geom: Mapped[Any] = mapped_column(Geometry("LINESTRING", srid=4326), nullable=False)
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    road_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    highway: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # OSM highway class
    # OSM maxspeed (km/h) when tagged; NULL = use the class default
    # (config/route_scoring.json). Only route comparison uses it (T-47).
    maxspeed_kmh: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Aggregates; score/rqi/p_bad are NULL for a piece without frames.
    n_images: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # aggregated continuous score, canonical RQI scale
    rqi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # canonical RQI level (shared/rqi_scale.json)
    p_bad: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    # True when the unlabelled-area rule capped `confidence` (no human label
    # within segment_aggregation.json unlabelled_area.radius_km).
    unlabelled_area: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    capture_date_min: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    capture_date_max: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, default=utcnow, server_default=func.now())


class PairJudgment(Base):
    """One "which frame shows the worse road?" judgment (quick-rate pairwise
    mode). Relative judgments are more consistent than absolute grades; the
    ml/ pipeline fits a Bradley-Terry score from them (ml/pairwise_scores.py)."""

    __tablename__ = "pair_judgments"
    __table_args__ = (
        CheckConstraint("result IN ('A', 'B', 'EQUAL')", name="ck_pair_judgments_result"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Client-generated id: undo deletes by it, and a retried save is a no-op.
    client_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    frame_a_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # street_view_images.id
    frame_b_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(5), nullable=False)  # A / B worse, or EQUAL
    labeller: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    meta: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # model scores at the time, elapsed_ms
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, default=utcnow, server_default=func.now())


class Job(Base):
    """
    Background job tracking.
    """
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    status: Mapped[Optional[str]] = mapped_column(String, default="pending")
    current_step: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    progress: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    total: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(String, default="")
    error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    result: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)



class TrainingData(Base):
    """
    Stores manual training data for Machine Learning.
    Includes ground truth RQI, bounding boxes, tags, and metadata.
    """

    __tablename__ = "training_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_filename: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)  # Link to file on disk
    manual_rqi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Human ground truth on the canonical RQI scale (shared/rqi_scale.json)
    
    # Annotations: List of {id, label, x, y, w, h} OR {id, label, points: [[x,y], ...]} for polygons
    annotations: Mapped[Optional[Any]] = mapped_column(JSON, default=[]) 
    
    # Internal metrics (calculated from area %)
    rqi_area_percent: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    
    # Tags: List of strings e.g. ["shadow", "wet", "occlusion"]
    tags: Mapped[Optional[Any]] = mapped_column(JSON, default=[])

    # Optional user comment
    comment: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Flexible metadata bucket
    meta_data: Mapped[Optional[Any]] = mapped_column(JSON, default={})
    
    created_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
