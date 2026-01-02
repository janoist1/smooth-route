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
        training_entries = db.query(TrainingDataModel).limit(10).all()
        print("SAMPLES FROM TrainingData:")
        for t in training_entries:
            print(f"  Filename in DB: '{t.image_filename}'")
            
        images = db.query(StreetViewImage).limit(10).all()
        print("\nSAMPLES FROM StreetViewImage (after get_filename):")
        for img in images:
            print(f"  Raw URL: '{img.image_url}' -> Parsed: '{get_filename(img.image_url)}'")
            
    finally:
        db.close()

if __name__ == "__main__":
    diagnose()
