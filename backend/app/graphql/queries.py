import strawberry
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, text
import threading
import json
import datetime

from app.core.database import SessionLocal
from app.models.models import StreetViewImage, TrainingData as TrainingDataModel, Job as JobModel, User
from app.core.config import settings
from app.services.job_service import create_job, get_job
from app.services.map_aggregation import grid_cell_size_for_zoom
from app.core.settings_manager import settings_manager

from .types import Point, Job, TrainingData, ProcessRouteInput, TrainingDataInput, RunAnalysisInput, TrainingStats, TrainingPointsResponse, FilterMode, Setting, UpdateSettingInput, DetectInput, DetectPrediction, ReviewActionInput, ReviewActionResult, RqiModelInfo

from app.graphql.resolver_helpers import get_db_session, image_filename_from_url as get_filename
from app.graphql.permissions import IsAdmin, IsAuthenticated

@strawberry.type
class RouteStep:
    lat: float
    lng: float


@strawberry.type
class RouteData:
    points: List[RouteStep]


@strawberry.type
class Viewer:
    """The authenticated caller, as provisioned in the users table."""
    clerk_id: str
    email: Optional[str]
    role: str


@strawberry.type
class DailyCount:
    day: str
    count: int


@strawberry.type
class JobSummary:
    id: str
    status: str
    message: Optional[str]
    progress: int
    total: int
    created_at: Optional[datetime.datetime]
    completed_at: Optional[datetime.datetime]


@strawberry.type
class AdminStats:
    """Rudimentary usage / coverage / job monitoring for admins."""
    # Street View image usage (Google cost proxy: 1 stored image ≈ 1 billable
    # Street View Static request; the free tier is per calendar month).
    total_images: int
    images_this_month: int
    free_tier_limit: int
    billable_this_month: int
    images_per_day: List[DailyCount]
    # Coverage / analysis
    total_points: int
    analyzed_points: int
    pending_analysis: int
    rqi_good: int
    rqi_fair: int
    rqi_poor: int
    # Users & jobs
    total_users: int
    admin_users: int
    recent_jobs: List[JobSummary]


# Street View Static is an Essentials SKU: 10k free billable events per month.
STREET_VIEW_FREE_TIER = 10000




@strawberry.type
class Query:
    @strawberry.field
    def config(self) -> str:
        return settings.GOOGLE_MAPS_API_KEY or ""

    @strawberry.field
    def me(self, info: strawberry.Info) -> Optional[Viewer]:
        """Viewer info for the frontend (role drives admin-only UI)."""
        identity = info.context.get("identity")
        if identity is None:
            return None
        return Viewer(clerk_id=identity.clerk_id, email=identity.email, role=identity.role)

    # Costs a Google Directions API call per invocation — never anonymous.
    @strawberry.field(permission_classes=[IsAuthenticated])
    def get_route(self, origin: str, destination: str) -> Optional[RouteData]:
        from app.services.google_maps import google_maps_service
        try:
            # google_maps_service.get_route returns list of dicts {'lat': float, 'lng': float}
            polyline_points = google_maps_service.get_route(origin, destination)
            return RouteData(
                points=[RouteStep(lat=p['lat'], lng=p['lng']) for p in polyline_points]
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error fetching route: {e}")
            return None
    
    @strawberry.field(permission_classes=[IsAdmin])
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

    @strawberry.field(permission_classes=[IsAdmin])
    def available_models(self) -> List[str]:
        from app.core.paths import data_path

        models_dir = data_path("models")
        if not models_dir.is_dir():
            return []
        return sorted(path.name for path in models_dir.glob("*.pt"))

    @strawberry.field(permission_classes=[IsAdmin])
    def rqi_model_info(self) -> RqiModelInfo:
        """Read-only card for the live RQI (DINO) artifact — for the settings UI."""
        from app.services.dino_service import dino_service

        info = dino_service.model_info()
        if not info:
            return RqiModelInfo(available=False)
        return RqiModelInfo(available=True, **info)

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

            # Determine RQI source
            rqi_display_source = settings_manager.get_setting("rqi_display_source", "both")
            
            final_rqi_score = p.rqi_score
            rqi_source = "yolo"

            if rqi_display_source == "dino":
                if p.dino_rqi_score is not None:
                    final_rqi_score = p.dino_rqi_score
                    rqi_source = "dino"
                else:
                     rqi_source = "yolo_fallback"
            
            # If 'both' or 'yolo', we keep rqi_score as is (YOLO), and user can use dino_rqi_score separately.
            # But we set source explicitly.
            elif rqi_display_source == "both":
                rqi_source = "yolo" # Default primary is YOLO in 'both' mode

            return Point(
                id=p.id,
                latitude=p.latitude,
                longitude=p.longitude,
                heading=p.heading,
                pitch=p.pitch,
                image_url=f"images/{filename_for_training}" if filename_for_training else p.image_url,
                rqi_score=final_rqi_score,
                dino_rqi_score=p.dino_rqi_score,
                damage_count=p.damage_count or 0,
                damage_types=p.damage_types,
                analysis_metadata=p.analysis_metadata,
                created_at=p.created_at,
                rqi_source=rqi_source,
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

            filenames = [get_filename(x.image_url) for x in results if x.image_url]
            filenames = [f for f in filenames if f]
            
            training_map = {}
            if filenames:
                 td_results = db.query(TrainingDataModel).filter(TrainingDataModel.image_filename.in_(filenames)).all()
                 for td in td_results:
                     training_map[td.image_filename] = td

            # Fetch setting once
            rqi_display_source = settings_manager.get_setting("rqi_display_source", "both")

            final_points = []
            for x in results:
                fname = get_filename(x.image_url)
                td = training_map.get(fname)
                
                # Logic for score selection
                final_rqi_score = x.rqi_score
                rqi_source = "yolo"

                if rqi_display_source == "dino":
                    if x.dino_rqi_score is not None:
                        final_rqi_score = x.dino_rqi_score
                        rqi_source = "dino"
                    else:
                        rqi_source = "yolo_fallback"
                
                final_points.append(Point(
                    id=x.id,
                    latitude=x.latitude,
                    longitude=x.longitude,
                    heading=x.heading,
                    pitch=x.pitch,
                    image_url=f"images/{fname}" if x.image_url else None,
                    rqi_score=final_rqi_score,
                    dino_rqi_score=x.dino_rqi_score,
                    damage_count=x.damage_count or 0,
                    damage_types=x.damage_types,
                    analysis_metadata=x.analysis_metadata,
                    created_at=x.created_at,
                    rqi_source=rqi_source,
                    manual_rqi=td.manual_rqi if td else None,
                    manual_tags=td.tags if td else None,
                    manual_annotations=td.annotations if td else None,
                    manual_comment=td.comment if td else None
                ))

            return final_points
        finally:
            db.close()
    
    @strawberry.field
    def road_quality_grid(
        self, zoom: int, bbox: Optional[List[float]] = None
    ) -> strawberry.scalars.JSON:
        """Quality-grid overview for the zoomed-out map.

        Returns `{"cell": <deg>, "cells": [[swLat, swLng, avgRqi], …]}` — one
        row per populated grid cell, coloured client-side by AVERAGE RQI. This
        is density-independent on purpose: a densely-sampled good road stays
        green (a summed heatmap would falsely light it up). Coverage is shown by
        which cells are filled, quality by their colour. Anonymous like
        `points`. Effective score = dino_rqi_score → yolo rqi_score; cells with
        neither are skipped. `swLat/swLng` = the cell's south-west corner.
        """
        cell = grid_cell_size_for_zoom(zoom)
        params = {"cell": cell}
        where = ["COALESCE(dino_rqi_score, rqi_score) IS NOT NULL"]
        if bbox and len(bbox) == 4:
            min_lng, min_lat, max_lng, max_lat = bbox
            where.append("longitude BETWEEN :min_lng AND :max_lng")
            where.append("latitude BETWEEN :min_lat AND :max_lat")
            params.update(
                min_lng=min_lng, min_lat=min_lat, max_lng=max_lng, max_lat=max_lat
            )

        sql = text(
            f"""
            SELECT
              floor(latitude / :cell) * :cell AS sw_lat,
              floor(longitude / :cell) * :cell AS sw_lng,
              AVG(COALESCE(dino_rqi_score, rqi_score)) AS avg_rqi
            FROM street_view_images
            WHERE {" AND ".join(where)}
            GROUP BY floor(latitude / :cell), floor(longitude / :cell)
            """
        )

        db = get_db_session()
        try:
            rows = db.execute(sql, params).fetchall()
        finally:
            db.close()

        return {
            "cell": cell,
            "cells": [
                [round(row.sw_lat, 6), round(row.sw_lng, 6), round(float(row.avg_rqi), 2)]
                for row in rows
            ],
        }

    @strawberry.field(permission_classes=[IsAdmin])
    def admin_stats(self) -> AdminStats:
        """Aggregate usage/coverage/job stats for the admin monitoring page."""
        effective = func.coalesce(
            StreetViewImage.dino_rqi_score, StreetViewImage.rqi_score
        )
        month_start = datetime.datetime.utcnow().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        db = get_db_session()
        try:
            total_images = db.query(StreetViewImage).count()
            images_this_month = (
                db.query(StreetViewImage)
                .filter(StreetViewImage.created_at >= month_start)
                .count()
            )
            analyzed = db.query(StreetViewImage).filter(effective.isnot(None)).count()
            good = db.query(StreetViewImage).filter(effective <= 2.0).count()
            fair = db.query(StreetViewImage).filter(
                effective > 2.0, effective <= 3.0
            ).count()
            poor = db.query(StreetViewImage).filter(effective > 3.0).count()

            per_day_rows = db.execute(
                text(
                    """
                    SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                           COUNT(*) AS cnt
                    FROM street_view_images
                    WHERE created_at >= (now() - interval '13 days')
                    GROUP BY 1
                    ORDER BY 1
                    """
                )
            ).fetchall()

            total_users = db.query(User).count()
            admin_users = db.query(User).filter(User.role == "admin").count()

            recent = (
                db.query(JobModel)
                .order_by(JobModel.created_at.desc())
                .limit(10)
                .all()
            )

            return AdminStats(
                total_images=total_images,
                images_this_month=images_this_month,
                free_tier_limit=STREET_VIEW_FREE_TIER,
                billable_this_month=max(0, images_this_month - STREET_VIEW_FREE_TIER),
                images_per_day=[
                    DailyCount(day=r.day, count=r.cnt) for r in per_day_rows
                ],
                total_points=total_images,
                analyzed_points=analyzed,
                pending_analysis=total_images - analyzed,
                rqi_good=good,
                rqi_fair=fair,
                rqi_poor=poor,
                total_users=total_users,
                admin_users=admin_users,
                recent_jobs=[
                    JobSummary(
                        id=j.job_id,
                        status=j.status or "unknown",
                        message=j.message,
                        progress=j.progress or 0,
                        total=j.total or 0,
                        created_at=j.created_at,
                        completed_at=j.completed_at,
                    )
                    for j in recent
                ],
            )
        finally:
            db.close()

    @strawberry.field(permission_classes=[IsAdmin])
    def training_points(self, mode: FilterMode = FilterMode.ALL, limit: int = 20, offset: int = 0, model: str = "yolo") -> TrainingPointsResponse:
        db = get_db_session()
        try:
            query = db.query(StreetViewImage)
            
            # --- FILTERING LOGIC ---
            from sqlalchemy import or_
            # --- FILTERING LOGIC ---
            # Optimization: Avoid JOIN with OR/CONCAT which kills performance.
            # Instead, fetch relevant filenames first and use IN/NOT IN.
            
            # 1. Get Set of filenames that have evaluated score
            td_query = db.query(TrainingDataModel.image_filename).filter(TrainingDataModel.manual_rqi != None)
            
            evaluated_filenames = [r[0] for r in td_query.all()]
            
            # 2. Build lookups (both raw filename and with images/ prefix)
            # This covers the two standard patterns found in image_url
            lookup_urls = set(evaluated_filenames)
            lookup_urls.update([f"images/{f}" for f in evaluated_filenames])
            # Also handle absolute paths if they follow known patterns? 
            # adhering to the view logic: 'images/' prefix is the most common variation.
            
            if mode == FilterMode.PENDING:
                # PENDING: Not in the "evaluated" set
                # Note: NOT IN can be slow with NULLs, ensure column is not null or handle it.
                # Assuming image_url is significant.
                if lookup_urls:
                    query = query.filter(StreetViewImage.image_url.notin_(lookup_urls))
                
            elif mode == FilterMode.REVIEWED:
                 # REVIEWED: Must be in the "evaluated" set
                 if not lookup_urls:
                     # No reviewed items exists -> Empty result
                     return TrainingPointsResponse(items=[], total_count=0, has_more=False)
                 
                 query = query.filter(StreetViewImage.image_url.in_(lookup_urls))

            # --- SORTING ---
            query = query.order_by(StreetViewImage.id.desc())

            # --- PAGINATION & MAPPING ---
            total_count = query.count()
            items_db = query.offset(offset).limit(limit).all()
            
            # Helper to map to GraphQL type
            def map_point(p, td):
                return Point(
                    id=p.id,
                    latitude=p.latitude,
                    longitude=p.longitude,
                    heading=p.heading,
                    pitch=p.pitch,
                    image_url=p.image_url, # Assuming simple mapping, fix if needed
                    rqi_score=p.rqi_score,
                    dino_rqi_score=p.dino_rqi_score,
                    damage_count=p.damage_count or 0,
                    damage_types=p.damage_types,
                    analysis_metadata=p.analysis_metadata,
                    created_at=p.created_at,
                    manual_rqi=td.manual_rqi if td else None,
                    manual_tags=td.tags if td else None,
                    manual_annotations=td.annotations if td else None,
                    manual_comment=td.comment if td else None
                )

            # Helper to extract filename

            # Need to fetch training data for mapped items to populate manual fields
            # Optimization: Fetch TrainingData for these IDs/files
            filenames = [get_filename(p.image_url) for p in items_db]
            filenames = [f for f in filenames if f] # Filter Nones
            
            if filenames:
                tds = db.query(TrainingDataModel).filter(TrainingDataModel.image_filename.in_(filenames)).all()
                td_map = {t.image_filename: t for t in tds}
            else:
                td_map = {}

            items = []
            for p in items_db:
                fname = get_filename(p.image_url)
                items.append(map_point(p, td_map.get(fname)))

            return TrainingPointsResponse(
                items=items,
                total_count=total_count,
                has_more=(offset + len(items) < total_count)
            )
            
        finally:
            db.close()

    @strawberry.field(permission_classes=[IsAdmin])
    def training_stats(self, mode: FilterMode = FilterMode.ALL, is_dino: bool = False) -> TrainingStats:
        db = get_db_session()
        try:
            import os

            # 1. Fetch training data (manual ground truth)
            training_entries = db.query(TrainingDataModel).all()
            # Map filename to TrainingData object for O(1) lookup
            training_map = {t.image_filename: t for t in training_entries}
            
            from app.models.models import StreetViewImage
            # 2. Get points based on mode
            # Optimization: Filter in DB if possible, but filename extration makes it hard.
            # For now, fetch all but use optimized lookup.
            query = db.query(StreetViewImage)
            all_candidates = query.all()

            relevant_points = []
            for c in all_candidates:
                fname = get_filename(c.image_url)
                in_training = fname in training_map
                
                if mode == FilterMode.PENDING:
                    if not in_training:
                        relevant_points.append(c)
                    elif training_map[fname].manual_rqi is None:
                         relevant_points.append(c)

                elif mode == FilterMode.REVIEWED:
                    if in_training and training_map[fname].manual_rqi is not None:
                        relevant_points.append(c)
                else: # ALL
                    relevant_points.append(c)

            total = len(relevant_points)
            
            # Count annotated within relevant
            annotated_count = 0
            for p in relevant_points:
                fname = get_filename(p.image_url)
                td = training_map.get(fname)
                if td and td.manual_rqi is not None: annotated_count += 1
            
            annotated = annotated_count
            pending = total - annotated
            
            # Quality stats (Prioritize Manual RQI over AI RQI)
            effective_scores = []
            for p in relevant_points:
                fname = get_filename(p.image_url)
                td = training_map.get(fname)
                
                if td and td.manual_rqi is not None:
                     effective_scores.append(td.manual_rqi)
                elif is_dino and p.dino_rqi_score is not None:
                    effective_scores.append(p.dino_rqi_score)
                elif not is_dino and p.rqi_score is not None:
                    effective_scores.append(p.rqi_score)
            
            avg_rqi = sum(effective_scores) / len(effective_scores) if effective_scores else 0.0
            
            good = len([s for s in effective_scores if s <= 2.0])
            fair = len([s for s in effective_scores if 2.0 < s <= 3.5])
            poor = len([s for s in effective_scores if s > 3.5])

            rqi1 = len([s for s in effective_scores if s < 1.5])
            rqi2 = len([s for s in effective_scores if 1.5 <= s < 2.5])
            rqi3 = len([s for s in effective_scores if 2.5 <= s < 3.5])
            rqi4 = len([s for s in effective_scores if 3.5 <= s < 4.5])
            rqi5 = len([s for s in effective_scores if s >= 4.5])

            # 5. Pending analysis count (images without RQI score)
            if is_dino:
                pending_analysis_count = db.query(StreetViewImage).filter(StreetViewImage.dino_rqi_score.is_(None)).count()
            else:
                pending_analysis_count = db.query(StreetViewImage).filter(StreetViewImage.rqi_score.is_(None)).count()

            return TrainingStats(
                total=total,
                pending=pending,
                annotated=annotated,
                avg_rqi=float(avg_rqi),
                good_count=good,
                fair_count=fair,
                poor_count=poor,
                rqi1_count=rqi1,
                rqi2_count=rqi2,
                rqi3_count=rqi3,
                rqi4_count=rqi4,
                rqi5_count=rqi5,
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


    @strawberry.field(permission_classes=[IsAdmin])
    def next_training_point(self, current_id: int, mode: FilterMode = FilterMode.ALL, model: str = "yolo") -> Optional[int]:
        db = get_db_session()
        try:
            import os
            from app.models.models import StreetViewImage
            

            # Pre-fetch training tags for filtering
            training_entries = db.query(TrainingDataModel).all()
            training_files = {t.image_filename: t for t in training_entries}
            
            # Find next smaller ID (descending order)
            query = db.query(StreetViewImage).filter(StreetViewImage.id < current_id).order_by(StreetViewImage.id.desc())
            
            batch_size = 50
            offset = 0
            
            while True:
                batch = query.offset(offset).limit(batch_size).all()
                if not batch:
                    return None
                    
                for p in batch:
                    fname = get_filename(p.image_url)
                    td = training_files.get(fname)
                    
                    is_valid = True
                    if mode == FilterMode.PENDING:
                        if td and td.manual_rqi is not None: is_valid = False
                    elif mode == FilterMode.REVIEWED:
                        if not td or td.manual_rqi is None: is_valid = False
                            
                    if is_valid:
                        return p.id
                        
                offset += batch_size
                if offset > 2000: # Safety break (allow skipping more)
                    return None
                    
        finally:
            db.close()

