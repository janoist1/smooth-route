import strawberry
from typing import List, Optional
import datetime
from strawberry.scalars import JSON

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
    created_at: datetime.datetime
    
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
    job_id: str
    status: str
    current_step: Optional[str]
    progress: int
    total: int
    message: str
    error: Optional[str]
    result: Optional[JSON]
    created_at: datetime.datetime
    completed_at: Optional[datetime.datetime]

@strawberry.input
class ProcessRouteInput:
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float

@strawberry.input
class TrainingDataInput:
    image_filename: str
    manual_rqi: Optional[float] = None
    annotations: Optional[JSON] = None
    tags: Optional[List[str]] = None
    manual_comment: Optional[str] = None
    meta_data: Optional[JSON] = None
