import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.database import SessionLocal
from app.models.models import StreetViewImage, TrainingData as TrainingDataModel
from app.services.road_quality import road_quality_service, DamageDetection

def get_filename(url):
    if not url: return None
    if url.startswith("images/"): return url.replace("images/", "")
    if "/data/images/" in url: return url.split("/data/images/")[-1]
    if url.startswith("http"): return url.split("/")[-1]
    return os.path.basename(url)

def verify():
    db = SessionLocal()
    try:
        training_entries = db.query(TrainingDataModel).all()
        manual_scores = {t.image_filename: t.manual_rqi for t in training_entries if t.manual_rqi is not None}
        
        all_images = db.query(StreetViewImage).all()
        
        results = []
        for img in all_images:
            fname = get_filename(img.image_url)
            if fname in manual_scores:
                # Re-calculate RQI using detections and NEW logic
                # Extract detections from analysis_metadata if available
                meta = img.analysis_metadata or {}
                
                # Check if it was YOLO or Heuristic
                if meta.get("method") == "improved_heuristic_v4_configurable":
                    # Heuristic recalibration test
                    damage_score = meta.get("damage_score", 0.0)
                    # Use the logic from road_quality.py (re-implementing here to avoid re-running CV2)
                    threshold_excellent = 22.0
                    threshold_good = 35.0
                    threshold_fair = 50.0
                    threshold_poor = 65.0
                    
                    if damage_score < threshold_excellent: new_rqi = 1.0
                    elif damage_score < threshold_good: new_rqi = 2.0
                    elif damage_score < threshold_fair: new_rqi = 3.0
                    elif damage_score < threshold_poor: new_rqi = 4.0
                    else: new_rqi = 5.0
                else:
                    # YOLO recalibration test
                    # We'd need the raw detections. If not stored, we approximate.
                    # For simplicity, let's just see if the system-standard calculation works
                    # detections = [DamageDetection(...) for d in meta.get("detections", [])]
                    # Since we don't have all raw data here, let's look at the "Severe Conflicts" 
                    # from the previous script and see if they would be fixed.
                    new_rqi = img.rqi_score # Placeholder if we can't re-calculate
                
                results.append({
                    "id": img.id,
                    "old_rqi": img.rqi_score,
                    "new_rqi": new_rqi,
                    "manual": manual_scores[fname]
                })
        
        # Stats
        good_old = len([r for r in results if r['old_rqi'] <= 2.0])
        good_new = len([r for r in results if r['new_rqi'] <= 2.0])
        
        poor_old = len([r for r in results if r['old_rqi'] >= 4.0])
        poor_new = len([r for r in results if r['new_rqi'] >= 4.0])
        
        print(f"Total Reviewed: {len(results)}")
        print(f"Old distribution: Good={good_old}, Poor={poor_old}")
        print(f"New distribution: Good={good_new}, Poor={poor_new}")
        
    finally:
        db.close()

if __name__ == "__main__":
    verify()
