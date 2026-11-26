import strawberry
from typing import List, Optional
import datetime
from strawberry.scalars import JSON
from enum import Enum

from app.graphql.permissions import admin_only_field
from app.services.capture_date import format_capture_date

def street_view_link(
    latitude: float,
    longitude: float,
    heading: float,
    pitch: Optional[float] = None,
    pano_id: Optional[str] = None,
) -> str:
    """Free Google Maps Street View deep-link (no API call, no stored image).

    Uses the exact pano_id when available, else the coordinates (Google
    resolves the nearest panorama). One scheme for points and segments.
    """
    base = "https://www.google.com/maps/@?api=1&map_action=pano"
    view = f"&heading={heading}&pitch={pitch or 0}"
    if pano_id:
        return f"{base}&pano={pano_id}{view}"
    return f"{base}&viewpoint={latitude},{longitude}{view}"


# Segment links look down at the road like the analysed frames do.
SEGMENT_VIEW_PITCH = -20.0


@strawberry.enum
class FilterMode(Enum):
    ALL = "all"
    PENDING = "pending"
    REVIEWED = "reviewed"

@strawberry.type
class Point:
    id: int
    latitude: float
    longitude: float
    heading: float
    pitch: Optional[float]
    image_url: Optional[str]
    rqi_score: Optional[float]
    damage_count: int
    damage_types: Optional[JSON]
    analysis_metadata: Optional[JSON]
    dino_rqi_score: Optional[float] = None
    created_at: datetime.datetime
    rqi_source: str = "unknown"
    pano_id: Optional[str] = None
    # Street View panorama capture month (DB DATE, 1st of month). Exposed as
    # the "YYYY-MM" captureDate field below — month is the API's precision.
    capture_date_value: strawberry.Private[Optional[datetime.date]] = None

    # Manual Data (Joined) — the owner's labels: admin-only, null for others.
    manual_rqi: Optional[float] = admin_only_field()
    manual_tags: Optional[List[str]] = admin_only_field()
    manual_annotations: Optional[JSON] = admin_only_field()
    manual_comment: Optional[str] = admin_only_field()

    @strawberry.field
    def street_view_url(self) -> str:
        """Free Google Maps Street View deep-link (no API call, no stored image).

        Uses the exact pano_id when available, else the point's coordinates
        (Google resolves the nearest panorama).
        """
        return street_view_link(
            self.latitude, self.longitude, self.heading, self.pitch, self.pano_id
        )

    @strawberry.field
    def segment_id(self) -> Optional[strawberry.ID]:
        """The road segment (`RoadSegment.id`) this frame belongs to; null if
        it is not on a segment, or if the segment builder does not use the
        frame at all (not scored yet, or marked unusable) — so a non-null id
        always means the frame is among `segmentFrames(segmentId)`. Resolved
        with one small query per point — ask for it on a single `point`, not
        on a long `points` list.
        """
        from app.graphql.resolver_helpers import get_db_session
        from app.services.segment_aggregation import frame_score, frame_usable
        from app.services.segment_read import segment_id_for_point

        if (not frame_usable(self.analysis_metadata)
                or frame_score(self.dino_rqi_score, self.analysis_metadata) is None):
            return None

        db = get_db_session()
        try:
            found = segment_id_for_point(db, self.latitude, self.longitude, self.heading)
        finally:
            db.close()
        return strawberry.ID(found) if found else None

    @strawberry.field
    def capture_date(self) -> Optional[str]:
        """When Google captured the Street View image ("YYYY-MM"); null = unknown.

        The RQI describes the road as of this month, not as of createdAt
        (our download time). Readable anonymously, incl. the read-only deploy.
        """
        return format_capture_date(self.capture_date_value)

    # Derived/Computed fields can go here
    @strawberry.field
    def local_image_path(self) -> Optional[str]:
        # Logic to return relative path for frontend
        if not self.image_url:
            return None
        if self.image_url.startswith("images/"):
            return f"/api/v1/images/{self.image_url.replace('images/', '')}"
        # ... logic similar to REST ...
        return self.image_url

    def _meta_float(self, key: str) -> Optional[float]:
        meta = self.analysis_metadata
        if isinstance(meta, dict) and meta.get(key) is not None:
            try:
                return float(meta[key])
            except (TypeError, ValueError):
                return None
        return None

    @strawberry.field
    def dino_p_bad(self) -> Optional[float]:
        """Calibrated P(road is bad = Közepes or worse) written by the DINO pass."""
        return self._meta_float("dino_p_bad")

    @strawberry.field
    def dino_score(self) -> Optional[float]:
        """Continuous DINO RQI estimate on the canonical scale, before cutting into levels."""
        return self._meta_float("dino_score")

@strawberry.type
class TrainingData:
    id: int
    image_filename: str
    manual_rqi: Optional[float]
    annotations: Optional[JSON]
    tags: Optional[List[str]]
    meta_data: Optional[JSON]
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime]

@strawberry.type
class Job:
    id: str
    status: str
    progress: int
    total: int
    message: str
    type: str = "analysis" # 'analysis' or 'training'
    current_step: Optional[str] = None
    details: Optional[JSON] = None
    result: Optional[JSON] = None
    error: Optional[str] = None
    created_at: datetime.datetime = strawberry.field(default_factory=datetime.datetime.now)
    completed_at: Optional[datetime.datetime] = None

@strawberry.type
class TrainingStats:
    total: int
    pending: int
    annotated: int
    avg_rqi: float = strawberry.field(name="avgRqi")
    good_count: int = strawberry.field(name="goodCount")
    fair_count: int = strawberry.field(name="fairCount")
    poor_count: int = strawberry.field(name="poorCount")
    rqi1_count: int = strawberry.field(name="rqi1Count")
    rqi2_count: int = strawberry.field(name="rqi2Count")
    rqi3_count: int = strawberry.field(name="rqi3Count")
    rqi4_count: int = strawberry.field(name="rqi4Count")
    rqi5_count: int = strawberry.field(name="rqi5Count")
    pending_analysis: int = strawberry.field(name="pendingAnalysis")

@strawberry.type
class TrainingPointsResponse:
    items: List[Point]
    total_count: int
    has_more: bool

@strawberry.input
class RunAnalysisInput:
    strategy: str  # YOLO or CLASSIFICATION
    limit: int = 0
    reanalyze: bool = False

@strawberry.input
class ProcessRouteInput:
    origin: str
    destination: str
    path: Optional[List[List[float]]] = None

@strawberry.input
class TrainingDataInput:
    image_filename: str
    manual_rqi: Optional[float] = None
    annotations: Optional[JSON] = None
    tags: Optional[List[str]] = None
    manual_comment: Optional[str] = None
    meta_data: Optional[JSON] = None

@strawberry.type
class Setting:
    key: str
    value: JSON
    description: Optional[str] = None
    example: Optional[str] = None
    category: Optional[str] = None
    explanation: Optional[str] = None

@strawberry.input
class UpdateSettingInput:
    key: str
    value: JSON

@strawberry.type
class DetectPrediction:
    label: str
    confidence: float
    points: JSON # List of [x, y]

@strawberry.input
class DetectInput:
    filename: str
    conf_threshold: Optional[float] = None
    classes: Optional[List[str]] = None

@strawberry.type
class Annotation:
    id: str
    label: str
    score: float
    type: str  # 'box' or 'polygon'
    points: JSON # List of [x, y]

@strawberry.input
class ReviewActionInput:
    action_type: str
    parameters: JSON # Flexible params (filename, options, etc.)

@strawberry.type
class ReviewActionResult:
    success: bool
    message: Optional[str] = None
    processed_image_url: Optional[str] = None
    annotations: Optional[List[Annotation]] = None


@strawberry.type
class RqiModelInfo:
    """Read-only card describing the live RQI artifact (from its metadata)."""
    available: bool
    version: Optional[int] = None
    backbone: Optional[str] = None
    recipe: Optional[str] = None
    head: Optional[str] = None
    n_train: Optional[int] = None
    qwk: Optional[float] = None
    mae: Optional[float] = None
    exact_acc: Optional[float] = None
    bad_road_acc: Optional[float] = None
    bad_road_auc: Optional[float] = None
    scale_meaning: Optional[str] = None
    # Where qwk/mae/... come from: "spatial_cv" (ml/model_card.json, matched to
    # the artifact hash: streets the model never saw) or "artifact" (the
    # artifact's own cv_metrics, possibly an older protocol).
    metrics_source: Optional[str] = None
    metrics_protocol: Optional[str] = None
    metrics_measured_on: Optional[str] = None
    segment_qwk: Optional[float] = None      # ~200 m road segments (map unit)
    segment_length_m: Optional[float] = None
    new_area_qwk: Optional[float] = None     # leave-one-area-out (a new region)


@strawberry.type
class RoadSegment:
    """A ~150 m piece of a real road (OSM geometry) with aggregated quality.

    Geometry © OpenStreetMap contributors (ODbL) — show the attribution
    wherever these paths are drawn.
    """
    id: strawberry.ID
    # [[lat, lng], ...]
    path: List[List[float]]
    # RQI level on the canonical scale (shared/rqi_scale.json, 5 = Kiváló); null
    # if the piece has no frames. backend/config/segment_aggregation.json's
    # "scale" block mirrors that file (a test keeps them equal).
    rqi: Optional[int]
    # Aggregated continuous score on the same scale.
    score: Optional[float]
    # Mean P(road is bad = Közepes or worse) of the frames, 0-1.
    p_bad: Optional[float]
    # 0-1, after the image-age factor.
    confidence: float
    # "high" | "medium" | "low"
    confidence_level: str
    n_images: int
    length_m: float
    road_name: Optional[str]
    highway: Optional[str]
    # Oldest / newest Street View capture month on the segment ("YYYY-MM").
    capture_date_min: Optional[str]
    capture_date_max: Optional[str]
    # Why the confidence is not high — the factor that limits it most:
    # "few_images" | "disagreement" | "near_threshold" | "old_images" |
    # "unlabelled_area" (no human label within the configured radius).
    # Null for a high-confidence segment.
    confidence_reason: Optional[str] = None
    # Midpoint of the piece + the road's bearing there (for streetViewUrl).
    mid_lat: strawberry.Private[Optional[float]] = None
    mid_lng: strawberry.Private[Optional[float]] = None
    mid_heading: strawberry.Private[Optional[float]] = None

    @strawberry.field
    def street_view_url(self) -> Optional[str]:
        """Street View deep-link at the middle of the segment, looking along
        the road (same scheme as `Point.streetViewUrl`)."""
        if self.mid_lat is None or self.mid_lng is None:
            return None
        return street_view_link(
            round(self.mid_lat, 6), round(self.mid_lng, 6),
            round(self.mid_heading or 0.0, 1), SEGMENT_VIEW_PITCH,
        )


@strawberry.type
class RouteQuality:
    """Quality summary of a planned route, from the road segments along it."""
    total_length_m: float
    # Length of the path that runs along a segment with data.
    covered_length_m: float
    # Metres per RQI class, BEST FIRST (Kiváló, Jó, Közepes, Rossz — the
    # scale's model levels best -> worst), whatever the numbering direction.
    # Always sums to coveredLengthM.
    length_by_rqi: List[float]
    # Length-weighted mean segment score over the covered part; null if none.
    mean_score: Optional[float]
    # Speed-weighted impact (lower is better, 0 = all Kiváló): the average
    # number of levels below Kiváló per measured metre, each metre weighted by
    # speed / 50 km/h (OSM maxspeed, else a class default). Ranks "Legsimább".
    impact_score: Optional[float] = None
    # Up to 5, worst first; segments with "low" confidence excluded.
    worst_segments: List[RoadSegment]
    # Class of the unrounded mean, using the same cut-points as segments.
    mean_rqi: Optional[int] = None
