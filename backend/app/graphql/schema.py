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
from app.core.settings_manager import settings_manager

from .types import Point, Job, TrainingData, ProcessRouteInput, TrainingDataInput, RunAnalysisInput, TrainingStats, TrainingPointsResponse, FilterMode, Setting, UpdateSettingInput, DetectInput, DetectPrediction

def get_db_session():
    return SessionLocal()

@strawberry.type
class Query:
    @strawberry.field
    def config(self) -> str:
        return settings.GOOGLE_MAPS_API_KEY or ""
    
    @strawberry.field
    def settings(self) -> List[Setting]:
        from app.core.settings_manager import settings_manager
        return [
            Setting(
                key=s.key,
                value=s.value,
                description=s.description,
                example=s.example,
                category=s.category,
                explanation=s.explanation
            ) for s in settings_manager.get_all_settings()
        ]

    @strawberry.field
    def available_models(self) -> List[str]:
        import glob
        import os
        models_dir = os.path.join(os.getcwd(), "data", "models")
        if not os.path.exists(models_dir):
            return []
        # Return relative paths or filenames of .pt files
        files = glob.glob(os.path.join(models_dir, "*.pt"))
        return [os.path.basename(f) for f in files]

    @strawberry.field
    def point(self, id: int) -> Optional[Point]:
        db = get_db_session()
        try:
            p = db.query(StreetViewImage).filter(StreetViewImage.id == id).first()
            if not p:
                return None
            
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

            return Point(
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
        finally:
            db.close()

    @strawberry.field
    def points(self, bbox: Optional[List[float]] = None, limit: int = 100, offset: int = 0) -> List[Point]:
        db = get_db_session()
        try:
            query = db.query(StreetViewImage)
            if bbox and len(bbox) == 4:
                min_lng, min_lat, max_lng, max_lat = bbox
                query = query.filter(
                    StreetViewImage.longitude >= min_lng,
                    StreetViewImage.longitude <= max_lng,
                    StreetViewImage.latitude >= min_lat,
                    StreetViewImage.latitude <= max_lat
                )
            
            results = query.offset(offset).limit(limit).all()

            import os
            def get_filename(url):
                if not url: return None
                if url.startswith("images/"): return url.replace("images/", "")
                if "/data/images/" in url: return url.split("/data/images/")[-1]
                if url.startswith("http"): return url.split("/")[-1]
                return os.path.basename(url)

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
                    image_url=f"images/{fname}" if x.image_url else None,
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
    def training_points(self, mode: FilterMode = FilterMode.ALL, limit: int = 100, offset: int = 0) -> TrainingPointsResponse:
        db = get_db_session()
        try:
            import os
            def get_filename(url):
                if not url: return None
                if url.startswith("images/"): return url.replace("images/", "")
                if "/data/images/" in url: return url.split("/data/images/")[-1]
                if url.startswith("http"): return url.split("/")[-1]
                return os.path.basename(url)

            # 1. Fetch TrainingData
            training_entries = db.query(TrainingDataModel).all()
            training_files = {t.image_filename: t for t in training_entries}
            
            # 2. Main query
            query = db.query(StreetViewImage)
            
            paged_results = []
            total_count = 0

            if mode == FilterMode.PENDING:
                # High RQI and NOT in training data
                all_unfiltered = query.order_by(StreetViewImage.id.desc()).all()
                filtered = [c for c in all_unfiltered if get_filename(c.image_url) not in training_files]
                total_count = len(filtered)
                paged_results = filtered[offset : offset + limit]
            
            elif mode == FilterMode.REVIEWED:
                # MUST be in training data
                all_unfiltered = query.order_by(StreetViewImage.id.desc()).all()
                filtered = [c for c in all_unfiltered if get_filename(c.image_url) in training_files]
                total_count = len(filtered)
                paged_results = filtered[offset : offset + limit]
            
            else: # ALL
                total_count = query.count()
                paged_results = query.order_by(StreetViewImage.id.desc()).offset(offset).limit(limit).all()

            # Convert to GraphQL Types
            result_list = []
            for p in paged_results:
                fname = get_filename(p.image_url)
                td = training_files.get(fname)
                
                result_list.append(Point(
                    id=p.id,
                    latitude=p.latitude,
                    longitude=p.longitude,
                    heading=p.heading,
                    pitch=p.pitch,
                    image_url=f"images/{fname}",
                    rqi_score=p.rqi_score,
                    damage_count=p.damage_count or 0,
                    damage_types=p.damage_types,
                    analysis_metadata=p.analysis_metadata,
                    created_at=p.created_at,
                    manual_rqi=td.manual_rqi if td else None,
                    manual_tags=td.tags if td else None,
                    manual_annotations=td.annotations if td else None,
                    manual_comment=td.comment if td else None
                ))
            
            return TrainingPointsResponse(
                items=result_list,
                total_count=total_count,
                has_more=(offset + limit) < total_count
            )
        finally:
            db.close()

    @strawberry.field
    def training_stats(self, mode: FilterMode = FilterMode.ALL) -> TrainingStats:
        db = get_db_session()
        try:
            import os
            def get_filename(url):
                if not url: return None
                if url.startswith("images/"): return url.replace("images/", "")
                if "/data/images/" in url: return url.split("/data/images/")[-1]
                if url.startswith("http"): return url.split("/")[-1]
                return os.path.basename(url)

            # 1. Fetch training data (manual ground truth)
            training_entries = db.query(TrainingDataModel).all()
            # Map filename to manual RQI score
            manual_scores = {t.image_filename: t.manual_rqi for t in training_entries if t.manual_rqi is not None}
            training_files = {t.image_filename for t in training_entries}
            
            from app.models.models import StreetViewImage
            # 2. Get points based on mode
            query = db.query(StreetViewImage)
            if mode == FilterMode.PENDING:
                candidates = query.all()
                relevant_points = [c for c in candidates if get_filename(c.image_url) not in training_files]
            elif mode == FilterMode.REVIEWED:
                candidates = query.all()
                relevant_points = [c for c in candidates if get_filename(c.image_url) in training_files]
            else: # ALL
                relevant_points = query.all()

            total = len(relevant_points)
            annotated_list = [p for p in relevant_points if get_filename(p.image_url) in training_files]
            annotated = len(annotated_list)
            pending = total - annotated
            
            # Quality stats (Prioritize Manual RQI over AI RQI)
            effective_scores = []
            for p in relevant_points:
                fname = get_filename(p.image_url)
                if fname in manual_scores:
                    effective_scores.append(manual_scores[fname])
                elif p.rqi_score is not None:
                    effective_scores.append(p.rqi_score)
            
            avg_rqi = sum(effective_scores) / len(effective_scores) if effective_scores else 0.0
            
            good = len([s for s in effective_scores if s <= 2.0])
            fair = len([s for s in effective_scores if 2.0 < s <= 3.5])
            poor = len([s for s in effective_scores if s > 3.5])

            # 5. Pending analysis count (images without RQI score)
            pending_analysis_count = db.query(StreetViewImage).filter(StreetViewImage.rqi_score.is_(None)).count()

            return TrainingStats(
                total=total,
                pending=pending,
                annotated=annotated,
                avg_rqi=float(avg_rqi),
                good_count=good,
                fair_count=fair,
                poor_count=poor,
                pending_analysis=pending_analysis_count
            )
        finally:
            db.close()

    @strawberry.field
    def job(self, id: str) -> Optional[Job]:
        j = get_job(id)
        if not j:
            return None
        return Job(
            id=j.job_id,
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

    @strawberry.field
    def active_job(self) -> Optional[Job]:
        from app.services.job_service import get_active_job
        j = get_active_job()
        if not j:
            return None
        return Job(
            id=j.job_id,
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

from app.api.routes import run_route_processing, run_analysis_job, run_training_job

@strawberry.type
class Mutation:
    @strawberry.mutation
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

    @strawberry.mutation
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

    @strawberry.mutation
    def run_analysis(self, input: RunAnalysisInput) -> Job:
        job_id = create_job()
        
        # Start background thread
        thread = threading.Thread(
            target=run_analysis_job, 
            args=(job_id, input.strategy, input.limit, input.reanalyze), 
            daemon=True
        )
        thread.start()
        
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

    @strawberry.mutation
    def start_model_training(self) -> Job:
        print("DEBUG: start_model_training mutation INVOKED")
        job_id = create_job()
        
        # Start background thread
        thread = threading.Thread(
            target=run_training_job, 
            args=(job_id,), 
            daemon=True
        )
        thread.start()
        
        return Job(
            id=job_id,
            status="pending",
            current_step="training",
            progress=0,
            total=0,
            message="Training started",
            error=None,
            result=None,
            created_at=datetime.datetime.utcnow(),
            completed_at=None
        )

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

    @strawberry.mutation
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

    @strawberry.mutation
    def stop_job(self, job_id: str) -> bool:
        from app.services.job_service import update_job
        update_job(job_id, status="cancelled", message="Folyamat leállítva a felhasználó által.", error="Job stopped by user")
        return True
    
    @strawberry.mutation
    def detect_objects(self, input: DetectInput) -> List[DetectPrediction]:
        from app.services.inference import inference_service
        import os
        from app.core.config import settings

        # Robust path resolution matching main.py
        data_dir = settings.DATA_DIR
        if not os.path.isabs(data_dir):
            # backend/app/graphql/schema.py -> backend/app/graphql -> backend/app -> backend
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            # backend -> project_root
            project_root = os.path.dirname(backend_dir)
            data_dir = os.path.join(project_root, data_dir)
        
        image_path = os.path.join(data_dir, "images", input.filename)
        
        # Call inference - let InferenceService handle missing files with logs
        results = inference_service.detect_objects(
            image_path, 
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

schema = strawberry.Schema(query=Query, mutation=Mutation)
