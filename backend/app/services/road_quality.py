"""
Road quality service facade.

Composes the focused units — route collection, image download, and YOLO damage
analysis — and orchestrates the per-point analysis pass. Kept as the single
`road_quality_service` entry point used by tasks.py and cli.py.
"""
from datetime import datetime
from typing import Dict, Optional

from app.core.database import SessionLocal
from app.core.paths import resolve_stored_image
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
        strategy: str = "YOLO",
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
                    score = dino_service.predict_score(path)
                    if score is not None:
                        rqi = dino_service.rqi_from_score(score)
                        p_bad = dino_service.p_bad_from_score(score)
                        img.dino_rqi_score = float(rqi)
                        # Keep YOLO damage_count/types; only touch DINO metadata.
                        img.analysis_metadata = {
                            **(img.analysis_metadata or {}),
                            "dino_strategy": "DINO Classification",
                            "dino_score": round(float(score), 3),
                            **({"dino_p_bad": round(p_bad, 3)} if p_bad is not None else {}),
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
        """Resolve a stored image_url from the canonical image directory."""
        path = resolve_stored_image(image_url)
        return str(path) if path else None


# Singleton instance
road_quality_service = RoadQualityService()
