import strawberry
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import threading
import json
import datetime

from app.core.database import SessionLocal
from app.models.models import StreetViewImage, TrainingData as TrainingDataModel, Job as JobModel
from app.core.paths import image_path
from app.services.job_service import create_job, get_job
from app.core.settings_manager import settings_manager

from .types import Point, Job, TrainingData, ProcessRouteInput, TrainingDataInput, RunAnalysisInput, TrainingStats, TrainingPointsResponse, FilterMode, Setting, UpdateSettingInput, DetectInput, DetectPrediction, ReviewActionInput, ReviewActionResult

from app.graphql.resolver_helpers import get_db_session
from app.graphql.permissions import IsAdmin, IsAuthenticated


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAdmin])
    def update_setting(self, input: UpdateSettingInput) -> Setting:
        from app.core.settings_manager import settings_manager
        updated = settings_manager.update_setting(input.key, input.value)
        if not updated:
            raise Exception(f"Setting {input.key} not found")
        return Setting(
            key=updated.key,
            value=updated.value,
            description=updated.description,
            example=updated.example,
            category=updated.category,
            explanation=updated.explanation
        )

    @strawberry.mutation(permission_classes=[IsAdmin])
    def apply_preset(self, values: strawberry.scalars.JSON) -> List[Setting]:
        from app.core.settings_manager import settings_manager
        updated_settings = []
        for key, value in values.items():
            updated = settings_manager.update_setting(key, value)
            if updated:
                updated_settings.append(Setting(
                    key=updated.key,
                    value=updated.value,
                    description=updated.description,
                    example=updated.example,
                    category=updated.category,
                    explanation=updated.explanation
                ))
        return updated_settings

    @strawberry.mutation(permission_classes=[IsAdmin])
    def run_analysis(self, input: RunAnalysisInput) -> Job:
        from app.services.job_runner import job_runner
        from app.services.tasks import run_analysis_job
        
        job_id = create_job()
        
        # Start background task
        job_runner.run_background_task(
            target=run_analysis_job, 
            args=(job_id, input.strategy, input.limit, input.reanalyze)
        )
        
        return Job(
            id=job_id,
            status="pending",
            current_step="analyzing",
            progress=0,
            total=0,
            message=f"Analysis started ({input.strategy})",
            error=None,
            result=None,
            created_at=datetime.datetime.utcnow(),
            completed_at=None
        )

    @strawberry.mutation(permission_classes=[IsAdmin])
    def start_model_training(self) -> Job:
        from app.services.job_runner import job_runner
        from app.services.tasks import run_training_job
        
        print("DEBUG: start_model_training mutation INVOKED (YOLO)")
        job_id = create_job()
        
        # Start background process
        job_runner.run_background_task(
            target=run_training_job, 
            args=(job_id,)
        )
        
        return Job(
            id=job_id,
            status="pending",
            current_step="training",
            progress=0,
            total=0,
            message="Training started (Background Process)",
            error=None,
            result=None,
            created_at=datetime.datetime.utcnow(),
            completed_at=None
        )

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def process_route(self, input: ProcessRouteInput) -> Job:
        from app.services.job_runner import job_runner
        from app.services.tasks import run_route_processing
        
        job_id = create_job()
        
        # Start background task
        job_runner.run_background_task(
            target=run_route_processing, 
            args=(job_id, input.origin, input.destination)
        )
        
        # Return initial job state
        return Job(
            id=job_id,
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

    @strawberry.mutation(permission_classes=[IsAdmin])
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

    @strawberry.mutation(permission_classes=[IsAdmin])
    def delete_training_data(self, image_filename: str) -> bool:
        db = get_db_session()
        try:
            existing = (
                db.query(TrainingDataModel)
                .filter(TrainingDataModel.image_filename == image_filename)
                .first()
            )
            if existing:
                db.delete(existing)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            raise Exception(f"Failed to delete: {str(e)}")
        finally:
            db.close()

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def stop_job(self, job_id: str) -> bool:
        from app.services.job_service import update_job
        update_job(job_id, status="cancelled", message="Folyamat leállítva a felhasználó által.", error="Job stopped by user")
        return True
    
    @strawberry.mutation(permission_classes=[IsAdmin])
    def detect_objects(self, input: DetectInput) -> List[DetectPrediction]:
        from app.services.inference import inference_service

        path = image_path(input.filename)
        if not path.is_file():
            raise Exception(f"Image {input.filename} not found")
        
        results = inference_service.detect_objects(
            str(path),
            conf_threshold=input.conf_threshold,
            classes=input.classes
        )
        
        predictions = []
        for res in results:
             predictions.append(DetectPrediction(
                 label=res['label'],
                 confidence=res['confidence'],
                 points=res['points']
             ))
        return predictions

    @strawberry.mutation(permission_classes=[IsAdmin])
    def perform_review_action(self, input: ReviewActionInput) -> ReviewActionResult:
        from app.services.review_service import review_service
        
        # Convert scalar JSON to dict if necessary
        params = input.parameters
        if not isinstance(params, dict):
             # Handle if it comes as something else (depends on scalar impl)
             import json
             try:
                 params = json.loads(str(params))
             except:
                 params = {}

        result = review_service.perform_action(input.action_type, params)
        
        # Convert raw dict result to Typed Object
        # Handle annotations mapping separately if needed, but for now assuming direct mapping matches
        from .types import Annotation as AnnotationType, ReviewActionResult
        
        annot_objs = None
        if "annotations" in result:
            annot_objs = []
            for a in result["annotations"]:
                annot_objs.append(AnnotationType(
                    id=a['id'],
                    label=a['label'],
                    score=a['score'],
                    type=a['type'],
                    points=a['points']
                ))
        
        return ReviewActionResult(
            success=True,
            message=result.get("message"),
            processed_image_url=result.get("processedImageUrl"),
            annotations=annot_objs
        )

    @strawberry.mutation(permission_classes=[IsAdmin])
    def predict_dino_rqi(self, image_filename: str) -> Optional[int]:
        from app.services.dino_service import dino_service

        path = image_path(image_filename)
        if not path.is_file():
            raise Exception(f"Image {image_filename} not found")

        score = dino_service.predict_rqi(str(path))
        
        # Optionally save the result to DB automatically?
        # For now, just return it.
        if score:
            db = get_db_session()
            try:
                img = db.query(StreetViewImage).filter(StreetViewImage.image_url.like(f"%{image_filename}")).first()
                if img:
                    img.dino_rqi_score = float(score)
                    db.commit()
            finally:
                db.close()

        return score
