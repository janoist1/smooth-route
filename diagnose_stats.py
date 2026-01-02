import os
import sys

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
        manual_scores = {t.image_filename: t.manual_rqi for t in training_entries}
        
        all_images = db.query(StreetViewImage).all()
        
        # Mode: REVIEWED (which is what user seems to be looking at)
        reviewed_scores = []
        training_filenames = {t.image_filename for t in training_entries}
        
        good = 0
        fair = 0
        poor = 0
        
        for img in all_images:
            fname = get_filename(img.image_url)
            if fname in training_filenames:
                score = manual_scores.get(fname)
                if score is None:
                    score = img.rqi_score
                
                if score is not None:
                    reviewed_scores.append(score)
                    if score <= 2.0: good += 1
                    elif score <= 3.5: fair += 1
                    else: poor += 1
        
        avg = sum(reviewed_scores) / len(reviewed_scores) if reviewed_scores else 0
        print(f"REVIEWED MODE STATS:")
        print(f"  Count: {len(reviewed_scores)}")
        print(f"  Avg: {avg:.2f}")
        print(f"  Good: {good}")
        print(f"  Fair: {fair}")
        print(f"  Poor: {poor}")
        
    finally:
        db.close()

if __name__ == "__main__":
    diagnose()
