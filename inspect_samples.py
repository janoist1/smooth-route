import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.database import SessionLocal
from app.models.models import TrainingData as TrainingDataModel

def diagnose():
    db = SessionLocal()
    try:
        # Get samples from both ends
        good_samples = db.query(TrainingDataModel).filter(TrainingDataModel.manual_rqi <= 2.0).limit(5).all()
        poor_samples = db.query(TrainingDataModel).filter(TrainingDataModel.manual_rqi >= 4.0).limit(5).all()
        
        print("GOOD SAMPLES (RQI <= 2.0):")
        for s in good_samples:
            print(f"  ID: {s.id}, RQI: {s.manual_rqi}, Tags: {s.tags}, Comment: {s.comment}")
            
        print("\nPOOR SAMPLES (RQI >= 4.0):")
        for s in poor_samples:
            print(f"  ID: {s.id}, RQI: {s.manual_rqi}, Tags: {s.tags}, Comment: {s.comment}")
            
    finally:
        db.close()

if __name__ == "__main__":
    diagnose()
