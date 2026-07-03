
import os
import sys

# Ensure backend acts as package
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
backend_path = os.path.join(project_root, 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.core.config import settings
import os

def clean_orphaned_points():
    """
    Delete points from the database that do not have a corresponding image file on disk.
    Also delete points where the image file is 0 bytes (corrupted/failed download).
    """
    db = SessionLocal()
    try:
        points = db.query(StreetViewImage).all()
        print(f"Checking {len(points)} points for missing images...")
        
        deleted_count = 0
        
        images_dir = os.path.join(settings.resolve_data_dir(), "images")
        
        # We need to check where the file *actually* is.
        # The 'image_url' in DB is usually 'images/filename.jpg' or http URL.
        
        for point in points:
            should_delete = False
            
            if not point.image_url:
                should_delete = True
            elif point.image_url.startswith("http"):
                # Still HTTP -> Not downloaded yet -> Delete?
                # User asked: "törli azokat a pontokat, melyekhez nincs kép"
                # If it's HTTP, there isn't a local image file.
                should_delete = True
            else:
                # Local path format: "images/filename.jpg"
                filename = point.image_url.replace("images/", "")
                
                candidate = os.path.join(images_dir, filename)
                found_path = candidate if os.path.exists(candidate) else None
                
                if not found_path:
                    should_delete = True
                    # print(f"Missing file for point {point.id}: {filename}")
                else:
                    # Check size
                    if os.path.getsize(found_path) == 0:
                        should_delete = True
                        print(f"Empty file for point {point.id}: {found_path}")
                        try:
                            os.remove(found_path) # Clean up empty file
                        except:
                            pass

            if should_delete:
                db.delete(point)
                deleted_count += 1
        
        db.commit()
        print(f"Deleted {deleted_count} points without valid images.")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clean_orphaned_points()
