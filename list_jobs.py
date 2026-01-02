from app.core.database import SessionLocal
from app.models.models import Job
from app.services.job_service import JobStatus

db = SessionLocal()
try:
    jobs = db.query(Job).filter(Job.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value])).all()
    for job in jobs:
        print(f"ID: {job.job_id}, Status: {job.status}, Message: {job.message}")
finally:
    db.close()
