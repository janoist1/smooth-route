import os
import sys
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.database import SessionLocal
from app.models.models import StreetViewImage, TrainingData as TrainingDataModel

def get_filename(url):
    if not url: return None
    if url.startswith("images/"): return url.replace("images/", "")
    if "/data/images/" in url: return url.split("/data/images/")[-1]
    if url.startswith("http"): return url.split("/")[-1]
    return os.path.basename(url)

def diagnose():
    db = SessionLocal()
    try:
        training_entries = db.query(TrainingDataModel).all()
        manual_scores = {t.image_filename: t.manual_rqi for t in training_entries if t.manual_rqi is not None}
        
        all_images = db.query(StreetViewImage).all()
        
        data = []
        for img in all_images:
            fname = get_filename(img.image_url)
            if fname in manual_scores and img.rqi_score is not None:
                # We need the weights. Since we don't store raw weights in DB easily, 
                # we can approximate from detections or just look at metadata if available
                meta = img.analysis_metadata or {}
                # The road_quality_service might have stored total_weight in metadata
                # Let's check a sample
                data.append({
                    "id": img.id,
                    "manual": manual_scores[fname],
                    "ai": img.rqi_score,
                    "detections": img.damage_types
                })
        
        print(f"Sample Data (First 10):")
        for d in data[:10]:
            print(f"  ID {d['id']}: Manual {d['manual']}, AI {d['ai']}, Detections: {d['detections']}")
            
    finally:
        db.close()

if __name__ == "__main__":
    diagnose()
