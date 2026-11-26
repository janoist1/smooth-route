import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path so we can import app
project_root = os.getcwd()
backend_dir = os.path.join(project_root, "backend")
sys.path.append(backend_dir)

# Now we can import app modules
try:
    from app.core.config import settings
    from app.models.models import StreetViewImage
    from app.services.sv_client import StreetViewError, StreetViewFatal, default_client
    from app.services.sv_quota import DEFAULT_JOB_CAP, JobBudget, QuotaExceeded, cap_from_env
except ImportError as e:
    print(f"❌ Error importing backend modules: {e}")
    print("Ensure you are running this from the project root.")
    sys.exit(1)

# Setup DB
# Use the DATABASE_URL from settings or environment
db_url = os.getenv("DATABASE_URL") or settings.DATABASE_URL
engine = create_engine(db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def redownload_all_images(new_pitch=-20.0):
    db = SessionLocal()
    try:
        images = db.query(StreetViewImage).all()
        print(f"🔄 Found {len(images)} images to process (New Pitch: {new_pitch}).")
        
        # Determine local directory
        data_dir = settings.resolve_data_dir()
        images_dir = os.path.join(data_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        success_count = 0
        error_count = 0
        client = default_client()
        budget = JobBudget(cap_from_env("GOOGLE_SV_JOB_CAP", DEFAULT_JOB_CAP))
        print(client.quota.summary(), f"| this run: at most {budget.cap} images")

        for i, img in enumerate(images):
            print(f"[{i+1}/{len(images)}] ID: {img.id} | {img.latitude}, {img.longitude} | Heading: {img.heading}")
            
            # Consistent filename format as used in processing_service.py
            filename = f"{img.id:05d}_{img.latitude:.6f}_{img.longitude:.6f}_{int(img.heading)}.jpg"
            filepath = os.path.join(images_dir, filename)
            
            # Download (with the desired pitch) and overwrite. Every request
            # goes through the shared Street View client: booked on the monthly
            # quota counter and this run's cap first, paced at ~1 request/s.
            # NOTE: this script re-fetches EVERY image — with the default caps
            # it stops long before finishing; that is intended.
            try:
                body = client.image(
                    lat=img.latitude, lng=img.longitude,
                    heading=img.heading, pitch=new_pitch, job=budget,
                )
            except (QuotaExceeded, StreetViewFatal) as stop:
                db.commit()
                print(f"\n🛑 Stopped after {success_count} images: {stop}")
                return
            except StreetViewError as e:
                print(f"  ❌ Skipped: {e}")
                error_count += 1
            else:
                with open(filepath, 'wb') as f:
                    f.write(body)

                # Update DB record
                img.pitch = new_pitch
                # Store RELATIVE path for portability
                img.image_url = f"images/{filename}"
                success_count += 1
                print(f"  ✅ Saved to {filename}")

            # Commit periodically
            if (i + 1) % 10 == 0:
                db.commit()
                
        db.commit()
        print(f"\n✨ Done! Success: {success_count}, Errors: {error_count}")
    finally:
        db.close()

if __name__ == "__main__":
    # Check for GOOGLE_MAPS_API_KEY
    if not settings.GOOGLE_MAPS_API_KEY:
        print("❌ GOOGLE_MAPS_API_KEY is not set.")
        sys.exit(1)
        
    redownload_all_images()
