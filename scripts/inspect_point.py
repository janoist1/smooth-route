
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

def inspect_point(point_id):
    db = SessionLocal()
    try:
        point = db.query(StreetViewImage).filter(StreetViewImage.id == point_id).first()
        if point:
            print(f"ID: {point.id}")
            print(f"Image URL: {point.image_url}")
            print(f"Lat/Lng: {point.latitude}, {point.longitude}")
        else:
            print(f"Point {point_id} not found.")
    finally:
        db.close()

if __name__ == "__main__":
    # User mentioned ID 2565 in filename sv_2565_...
    inspect_point(2565)
