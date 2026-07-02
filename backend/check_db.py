from app.core.database import SessionLocal
from app.models.models import StreetViewImage, TrainingData
from sqlalchemy import func

def check():
    db = SessionLocal()
    try:
        points_count = db.query(StreetViewImage).count()
        training_count = db.query(TrainingData).count()
        points_with_rqi = db.query(StreetViewImage).filter(StreetViewImage.rqi_score.isnot(None)).count()
        
        print(f"StreetViewImage count: {points_count}")
        print(f"StreetViewImage with RQI count: {points_with_rqi}")
        print(f"TrainingData (manual) count: {training_count}")
        
        if points_count > 0:
            p = db.query(StreetViewImage).first()
            print(f"First image sample: id={p.id}, url={p.image_url}, rqi={p.rqi_score}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check()
