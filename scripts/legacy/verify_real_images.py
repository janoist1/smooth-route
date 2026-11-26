import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.services.road_quality import road_quality_service

def verify():
    db = SessionLocal()
    try:
        # Pick 5 images that were "Very Poor" (5.0) before
        poor_images = db.query(StreetViewImage).filter(StreetViewImage.rqi_score >= 4.0).limit(10).all()
        
        print(f"{'ID':<6} | {'Old RQI':<8} | {'New RQI':<8} | {'Method'}")
        print("-" * 40)
        
        for img in poor_images:
            old_rqi = img.rqi_score
            fname = os.path.join("data/images", os.path.basename(img.image_url))
            
            if not os.path.exists(fname):
                # Fallback to current dir if backend/data/images doesn't exist locally
                fname = os.path.basename(img.image_url)
            
            if os.path.exists(fname):
                # We use analyze_image_simple (heuristic) as it's faster for verification
                result = road_quality_service.analyze_image_simple(fname)
                new_rqi = result.rqi_score
                print(f"{img.id:<6} | {old_rqi:<8.1f} | {new_rqi:<8.1f} | {result.analysis_metadata.get('method')}")
            else:
                print(f"{img.id:<6} | {old_rqi:<8.1f} | {'MISSING':<8} | File not found: {fname}")
                
    finally:
        db.close()

if __name__ == "__main__":
    verify()
