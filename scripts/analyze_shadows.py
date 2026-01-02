
import sys
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup path to import backend app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend')))

from app.models.models import TrainingData
from app.core.config import settings

# Direct DB connection
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def analyze_shadows():
    db = SessionLocal()
    try:
        data = db.query(TrainingData).all()
        print(f"Total training images: {len(data)}")
        
        shadow_boxes = 0
        mega_shadows = 0 # > 30% of image area
        
        # Standard street view size (approx) - or relative if stored relative
        # Frontend stores absolute pixels? checking types.ts: x,y,w,h are numbers.
        # Usually SV is 640x640 or similar in the UI context, but let's see.
        # Actually backend export logic normalizes them using image size.
        # Let's verify what the stored values look like.
        
        for entry in data:
            if not entry.annotations:
                continue
                
            # We don't know the image size here easily without opening the file, 
            # but we can look for "unusually large" boxes relative to others.
            # Or if the UI saves pixel coords, we can guess.
            # Let's inspect a few first.
            
            for ann in entry.annotations:
                if ann.get('label') == 'shadow':
                    shadow_boxes += 1
                    w = ann.get('w', 0)
                    h = ann.get('h', 0)
                    area = w * h
                    
                    # Assuming 640x360 or similar UI canvas?
                    # If w > 300 and h > 200, it's likely a mega box.
                    if w > 100 and h > 100: # Heuristic threshold for logging
                         print(f"Large Shadow detected in {entry.image_filename}: {w}x{h}")
                         if w * h > 50000: # Arbitrary "huge" threshold
                             mega_shadows += 1

        print(f"\nStats:")
        print(f"Total 'shadow' boxes: {shadow_boxes}")
        print(f"Likely 'Mega-Shadows' (>50k px area): {mega_shadows}")
        
    finally:
        db.close()

if __name__ == "__main__":
    analyze_shadows()
