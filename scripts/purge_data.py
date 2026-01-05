from app.models.models import TrainingData, StreetViewImage, Job
from app.core.database import SessionLocal

def purge_training_data():
    """
    Purges all manual annotations to start fresh for Pipeline 2.0.
    """
    db = SessionLocal()
    try:
        print("Purging all training annotations...")
        db.query(TrainingData).delete()
        
        # Also reset RQI and damage counts on points to allow re-analysis
        db.query(StreetViewImage).update({
            StreetViewImage.rqi_score: None,
            StreetViewImage.damage_count: 0,
            StreetViewImage.damage_types: None,
            StreetViewImage.analysis_metadata: None
        })
        
        db.commit()
        print("Purge successful.")
    except Exception as e:
        db.rollback()
        print(f"Purge failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    purge_training_data()
