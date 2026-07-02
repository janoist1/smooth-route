from app.core.database import SessionLocal, engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        print("Adding dino_rqi_score to street_view_images...")
        try:
            conn.execute(text("ALTER TABLE street_view_images ADD COLUMN dino_rqi_score FLOAT"))
            conn.commit()
            print("Added dino_rqi_score.")
        except Exception as e:
            print(f"Could not add dino_rqi_score (maybe already exists): {e}")

        print("Adding manual_dino_rqi to training_data...")
        try:
            conn.execute(text("ALTER TABLE training_data ADD COLUMN manual_dino_rqi FLOAT"))
            conn.commit()
            print("Added manual_dino_rqi.")
        except Exception as e:
            print(f"Could not add manual_dino_rqi (maybe already exists): {e}")

if __name__ == "__main__":
    migrate()
