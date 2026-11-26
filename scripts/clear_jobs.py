from app.core.database import SessionLocal
from app.models.models import Job
from app.services.job_service import JobStatus

db = SessionLocal()
try:
    jobs = db.query(Job).filter(Job.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value])).all()
    for job in jobs:
        print(f"Cancelling ID: {job.job_id}")
        job.status = JobStatus.CANCELLED.value
        job.message = "Zombi folyamat leállítva a rendszer által."
    db.commit()
    print("All stuck jobs cancelled.")
finally:
    db.close()
