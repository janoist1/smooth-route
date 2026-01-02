
import sys
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup path to import backend app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend')))

from app.models.models import TrainingData
from app.core.config import settings
from sqlalchemy.orm.attributes import flag_modified

# Direct DB connection
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def cleanup_shadows():
    db = SessionLocal()
    try:
        data = db.query(TrainingData).all()
        print(f"Scanning {len(data)} images for large shadow boxes...")
        
        modified_count = 0
        boxes_removed = 0
        tags_added = 0
        
        # Threshold: 15,000 pixels (approx 120x120 or 200x75)
        # This is safe because real impact potholes are rarely this huge/rectangular.
        AREA_THRESHOLD = 15000 
        
        for entry in data:
            if not entry.annotations:
                continue
            
            original_len = len(entry.annotations)
            new_annotations = []
            has_changes = False
            
            for ann in entry.annotations:
                is_large_shadow = False
                
                if ann.get('label') == 'shadow':
                    w = ann.get('w', 0)
                    h = ann.get('h', 0)
                    area = w * h
                    
                    if area > AREA_THRESHOLD:
                        is_large_shadow = True
                
                if is_large_shadow:
                    # Remove box, add tag
                    boxes_removed += 1
                    current_tags = entry.tags or []
                    if "shadow" not in current_tags:
                        current_tags.append("shadow")
                        # Also add 'high_contrast' if it helps later
                        # if "high_contrast" not in current_tags:
                        #    current_tags.append("high_contrast")
                        
                        entry.tags = current_tags
                        tags_added += 1
                        # Crucial for SQLAlchemy to notice JSON change inside list
                        flag_modified(entry, "tags") 
                        
                    has_changes = True
                    # Do NOT append to new_annotations (effectively deleting it)
                else:
                    new_annotations.append(ann)
            
            if has_changes:
                entry.annotations = new_annotations
                flag_modified(entry, "annotations")
                modified_count += 1
                
        if modified_count > 0:
            db.commit()
            print(f"\nCleanup Complete!")
            print(f"Images modified: {modified_count}")
            print(f"Mega-Shadow boxes deleted: {boxes_removed}")
            print(f"Shadow tags added: {tags_added}")
        else:
            print("\nNo large shadow boxes found to clean.")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_shadows()
