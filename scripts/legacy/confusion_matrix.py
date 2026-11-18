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

def get_cat(score):
    if score <= 2.0: return "GOOD"
    if score <= 3.5: return "FAIR"
    return "POOR"

def diagnose():
    db = SessionLocal()
    try:
        training_entries = db.query(TrainingDataModel).all()
        manual_scores = {t.image_filename: t.manual_rqi for t in training_entries if t.manual_rqi is not None}
        
        all_images = db.query(StreetViewImage).all()
        
        matches = 0
        conflicts = 0
        total = 0
        
        confusion_matrix = {
            "GOOD": {"GOOD": 0, "FAIR": 0, "POOR": 0},
            "FAIR": {"GOOD": 0, "FAIR": 0, "POOR": 0},
            "POOR": {"GOOD": 0, "FAIR": 0, "POOR": 0},
        }

        for img in all_images:
            fname = get_filename(img.image_url)
            if fname in manual_scores and img.rqi_score is not None:
                m_cat = get_cat(manual_scores[fname])
                a_cat = get_cat(img.rqi_score)
                confusion_matrix[m_cat][a_cat] += 1
                total += 1
                if m_cat == a_cat:
                    matches += 1
                elif (m_cat == "GOOD" and a_cat == "POOR") or (m_cat == "POOR" and a_cat == "GOOD"):
                    conflicts += 1
        
        print(f"Total Evaluated: {total}")
        print(f"Exact Category Matches: {matches} ({matches/total:.1%})")
        print(f"Severe Conflicts (Good vs Poor): {conflicts} ({conflicts/total:.1%})")
        
        print("\nConfusion Matrix (Rows=Manual, Cols=AI):")
        print("          AI: GOOD | FAIR | POOR")
        for m_cat in ["GOOD", "FAIR", "POOR"]:
            row = confusion_matrix[m_cat]
            print(f"Manual {m_cat:4}:  {row['GOOD']:3}  |  {row['FAIR']:3}  |  {row['POOR']:4}")
            
    finally:
        db.close()

if __name__ == "__main__":
    diagnose()
