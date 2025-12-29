import strawberry
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import threading
import json
import datetime

from app.core.database import SessionLocal
from app.models.models import StreetViewImage, TrainingData as TrainingDataModel, Job as JobModel
from app.core.config import settings
from app.api.routes import run_route_processing
from app.services.job_service import create_job, get_job

from .types import Point, Job, TrainingData, ProcessRouteInput, TrainingDataInput

def get_db_session():
    return SessionLocal()

@strawberry.type
class Query:
    @strawberry.field
    def config(self) -> str:
        # Just returning the key directly as a simple field, or a structured object?
        # The REST API returns {"google_maps_api_key": ...}
        # Let's return a simple object or string.
        # For simplicity, let's create a Config type ideally, but string is fine for now/
        # Actually returning a JSON string might be easiest if we didn't define a type.
        # But let's define a Config type inline or just return the key.
        return settings.GOOGLE_MAPS_API_KEY or ""

    @strawberry.field
    def point(self, id: int) -> Optional[Point]:
        db = get_db_session()
        try:
            p = db.query(StreetViewImage).filter(StreetViewImage.id == id).first()
            if not p:
                return None
            
            # Helper to parse filename similar to REST
            image_url = p.image_url
            filename_for_training = None
            if image_url:
                if image_url.startswith("images/"):
                    filename_for_training = image_url.replace("images/", "")
                elif "/data/images/" in image_url:
                    filename_for_training = image_url.split("/data/images/")[-1]
                elif image_url.startswith("http"):
                    filename_for_training = image_url.split("/")[-1]
                else:
                    import os
                    filename_for_training = os.path.basename(image_url)

            # Convert SQLAlchemy model to Strawberry Type
            # And merge manually training data
            # Note: Strawberry types are plain classes.
            
            # 2. Fetch Training Data override
            manual_rqi = None
            manual_tags = None
            manual_annotations = None
            manual_comment = None

            if filename_for_training:
                td = db.query(TrainingDataModel).filter(TrainingDataModel.image_filename == filename_for_training).first()
                if td:
                    manual_rqi = td.manual_rqi
                    manual_tags = td.tags
                    manual_annotations = td.annotations
                    manual_comment = td.comment

            # 3. Construct Point
            point_data = Point(
                id=p.id,
                latitude=p.latitude,
                longitude=p.longitude,
                heading=p.heading,
                pitch=p.pitch,
                image_url=f"images/{filename_for_training}" if filename_for_training else p.image_url,
                rqi_score=p.rqi_score,
                damage_count=p.damage_count or 0,
                damage_types=p.damage_types,
                analysis_metadata=p.analysis_metadata,
                created_at=p.created_at,
                manual_rqi=manual_rqi,
                manual_tags=manual_tags,
                manual_annotations=manual_annotations,
                manual_comment=manual_comment
            )
            
            return point_data
        finally:
            db.close()

    @strawberry.field
    def points(self, bbox: Optional[List[float]] = None, limit: int = 100, offset: int = 0) -> List[Point]:
        # bbox: [min_lng, min_lat, max_lng, max_lat]
        db = get_db_session()
        try:
            query = db.query(StreetViewImage)
            if bbox and len(bbox) == 4:
                min_lng, min_lat, max_lng, max_lat = bbox
                # Simple box filter
                query = query.filter(
                    StreetViewImage.longitude >= min_lng,
                    StreetViewImage.longitude <= max_lng,
                    StreetViewImage.latitude >= min_lat,
                    StreetViewImage.latitude <= max_lat
                )
            
            # Apply limit/offset
            # If bbox is present, we might want to increase limit or remove it? keeping it for safety.
            results = query.offset(offset).limit(limit).all()

            # Batch fetch training data
            # Logic matches single point resolver: parse filename from URL
            # To optimize, we'd preload or map them. For now, let's map in memory.
            
            # 1. Collect all filenames
            import os
            
            def get_filename(url):
                if not url: return None
                if url.startswith("images/"): return url.replace("images/", "")
                if "/data/images/" in url: return url.split("/data/images/")[-1]
                if url.startswith("http"): return url.split("/")[-1]
                return os.path.basename(url)

            # Map filename -> Point metadata
            # We can fetch all relevant TrainingData in one go if we had a list of filenames.
            # But "IN" clause with strings might be heavy. Let's do it simply loop for <100 items.
            # OR better: fetch all training data? No.

            # Let's just do it per item for now, or build a map if many items.
            # Since limit is 100, simple loop with batched query is better.
            
            filenames = [get_filename(x.image_url) for x in results if x.image_url]
            filenames = [f for f in filenames if f]
            
            training_map = {}
            if filenames:
                 td_results = db.query(TrainingDataModel).filter(TrainingDataModel.image_filename.in_(filenames)).all()
                 for td in td_results:
                     training_map[td.image_filename] = td

            final_points = []
            for x in results:
                fname = get_filename(x.image_url)
                td = training_map.get(fname)
                
                final_points.append(Point(
                    id=x.id,
                    latitude=x.latitude,
                    longitude=x.longitude,
                    heading=x.heading,
                    pitch=x.pitch,
                    image_url=f"images/{get_filename(x.image_url)}" if x.image_url else None,
                    rqi_score=x.rqi_score,
                    damage_count=x.damage_count or 0,
                    damage_types=x.damage_types,
                    analysis_metadata=x.analysis_metadata,
                    created_at=x.created_at,
                    manual_rqi=td.manual_rqi if td else None,
                    manual_tags=td.tags if td else None,
                    manual_annotations=td.annotations if td else None,
                    manual_comment=td.comment if td else None
                ))

            return final_points
        finally:
            db.close()

    @strawberry.field
    def job(self, id: str) -> Optional[Job]:
        j = get_job(id)
        if not j:
            return None
        return Job(
            job_id=j.job_id,
            status=j.status.value,
            current_step=j.current_step.value if j.current_step else None,
            progress=j.progress,
            total=j.total,
            message=j.message,
            error=j.error,
            result=j.result,
            created_at=j.created_at,
            completed_at=j.completed_at
        )

@strawberry.type
class Mutation:
    @strawberry.mutation
    def process_route(self, input: ProcessRouteInput) -> Job:
        job_id = create_job()
        origin = f"{input.origin_lat},{input.origin_lng}"
        destination = f"{input.destination_lat},{input.destination_lng}"

        # Start background thread
        thread = threading.Thread(
            target=run_route_processing, args=(job_id, origin, destination), daemon=True
        )
        thread.start()
        
        # Return initial job state
        return Job(
            job_id=job_id,
            status="pending",
            current_step=None,
            progress=0,
            total=0,
            message="Job started",
            error=None,
            result=None,
            created_at=datetime.datetime.utcnow(),
            completed_at=None
        )

    @strawberry.mutation
    def save_training_data(self, input: TrainingDataInput) -> str:
        db = get_db_session()
        try:
            existing = (
                db.query(TrainingDataModel)
                .filter(TrainingDataModel.image_filename == input.image_filename)
                .first()
            )
            
            if existing:
                existing.manual_rqi = input.manual_rqi
                existing.annotations = input.annotations
                existing.tags = input.tags
                existing.comment = input.manual_comment
                existing.meta_data = input.meta_data
                existing.updated_at = datetime.datetime.utcnow()
            else:
                new_entry = TrainingDataModel(
                    image_filename=input.image_filename,
                    manual_rqi=input.manual_rqi,
                    annotations=input.annotations,
                    tags=input.tags,
                    comment=input.manual_comment,
                    meta_data=input.meta_data,
                )
                db.add(new_entry)
            db.commit()
            return "success"
        except Exception as e:
            db.rollback()
            raise Exception(f"Failed to save: {str(e)}")
        finally:
            db.close()

schema = strawberry.Schema(query=Query, mutation=Mutation)
