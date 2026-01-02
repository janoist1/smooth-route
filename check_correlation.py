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
        training_entries = db.query(TrainingDataModel).all()
        manual_scores = {t.image_filename: t.manual_rqi for t in training_entries if t.manual_rqi is not None}
        
        all_images = db.query(StreetViewImage).all()
        
        pairs = []
        for img in all_images:
            fname = get_filename(img.image_url)
            if fname in manual_scores and img.rqi_score is not None:
                pairs.append((img.rqi_score, manual_scores[fname]))
        
        if not pairs:
            print("No matching pairs found.")
            return

        # Calculate correlation
        from statistics import mean
        
        n = len(pairs)
        x = [p[0] for p in pairs]
        y = [p[1] for p in pairs]
        
        mean_x = mean(x)
        mean_y = mean(y)
        
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        denominator_y = sum((y[i] - mean_y) ** 2 for i in range(n))
        
        correlation = numerator / ( (denominator_x * denominator_y) ** 0.5 ) if denominator_x and denominator_y else 0
        
        print(f"Data Points: {n}")
        print(f"Correlation (AI vs Manual): {correlation:.4f}")
        
        if correlation < 0:
            print("WARNING: Negative correlation detected! Scales might be inverted.")
        elif correlation < 0.3:
            print("Low correlation detected.")
        else:
            print("Positive correlation detected. Scale usage seems consistent.")
            
    finally:
        db.close()

if __name__ == "__main__":
    diagnose()
