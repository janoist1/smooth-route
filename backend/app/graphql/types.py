import strawberry
from typing import List, Optional
import datetime
from strawberry.scalars import JSON
from enum import Enum

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
    rqi_source: str = "yolo" 
    
    # Manual Data (Joined)
    manual_rqi: Optional[float] = None
    manual_tags: Optional[List[str]] = None
    manual_annotations: Optional[JSON] = None
    manual_comment: Optional[str] = None

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
    created_at: datetime.datetime = datetime.datetime.now
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
