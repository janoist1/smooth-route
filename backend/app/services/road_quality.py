"""
Road quality service facade.

Composes the focused units — route collection, image download, and YOLO damage
analysis — and orchestrates the per-point analysis pass. Kept as the single
`road_quality_service` entry point used by tasks.py and cli.py.
"""
import os
from datetime import datetime
from typing import Dict, Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.services import image_downloader, route_collector
from app.services.dino_service import dino_service
from app.services.job_service import JobStep, update_job
from app.services.road_analyzer import RoadDamageAnalyzer

# Re-exported for backward compatibility.
from app.services.rqi_scoring import (  # noqa: F401
    DAMAGE_CLASSES,
    DAMAGE_NAMES,
    DamageDetection,
    RoadQualityResult,
)


class RoadQualityService:
    """Facade over the road-quality pipeline stages."""

    def __init__(self):
        self.analyzer = RoadDamageAnalyzer()

    # --- Stage delegation -------------------------------------------------
    def analyze_image(self, image_path: str, confidence_threshold: Optional[float] = None):
        return self.analyzer.analyze_image(image_path, confidence_threshold)

    def collect_points(self, origin: str, destination: str, job_id: str):
        return route_collector.collect_points(origin, destination, job_id)

    def download_images(self, job_id: str):
        return image_downloader.download_images(job_id)

    # --- Orchestration ----------------------------------------------------
    def analyze_points(
        self,
        job_id: str = None,
        strategy: str = "HEURISTIC",
        limit: int = 0,
        reanalyze: bool = False,
    ) -> Dict:
        """Step 3: analyze stored points using the selected strategy."""
        db = SessionLocal()
        try:
            query = db.query(StreetViewImage)
            if not reanalyze:
                if strategy == "CLASSIFICATION":
                    query = query.filter(StreetViewImage.dino_rqi_score == None)  # noqa: E711
                else:
                    query = query.filter(StreetViewImage.rqi_score == None)  # noqa: E711

            images = query.limit(limit).all() if limit > 0 else query.all()
            total = len(images)
            analyzed_count = 0

            if job_id:
                update_job(job_id, current_step=JobStep.ANALYZING, progress=0, total=total,
                           message=f"Elemzés futtatása ({strategy})...")

            for i, img in enumerate(images):
                if job_id and i % 5 == 0:
                    update_job(job_id, progress=i, total=total, message=f"Elemzés: {i}/{total}")

                if not img.image_url:
                    continue

                path = self._resolve_image_path(img.image_url)
                if not path:
                    continue

                if strategy == "CLASSIFICATION":
                    print(f"DEBUG: Running DINO classification for {path}")
                    rqi = dino_service.predict_rqi(path)
                    if rqi is not None:
                        img.dino_rqi_score = float(rqi)
                        # Keep YOLO damage_count/types; only touch DINO metadata.
                        img.analysis_metadata = {
                            **(img.analysis_metadata or {}),
                            "dino_strategy": "DINO Classification",
                            "dino_timestamp": str(datetime.utcnow()),
                        }
                        analyzed_count += 1
                else:
                    result = self.analyze_image(path)
                    img.rqi_score = result.rqi_score
                    img.damage_count = result.damage_count
                    img.damage_types = result.damage_types
                    img.analysis_metadata = result.analysis_metadata
                    analyzed_count += 1

            db.commit()
            return {"status": "success", "analyzed": analyzed_count, "strategy_used": strategy}
        except Exception as e:
            print(f"Error during analysis: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def _resolve_image_path(image_url: str) -> Optional[str]:
        """Resolve a stored image_url to an existing absolute path, or None."""
        fname = image_url.replace("images/", "") if image_url.startswith("images/") \
            else os.path.basename(image_url)

        candidates = [os.path.join(settings.resolve_data_dir(), "images", fname)]

        # Legacy: <project_root>/data/images and CWD-relative fallbacks.
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates.append(os.path.join(os.path.dirname(backend_dir), "data", "images", fname))
        candidates.append(os.path.join(os.getcwd(), "data", "images", fname))

        return next((p for p in candidates if os.path.exists(p)), None)


# Singleton instance
road_quality_service = RoadQualityService()
