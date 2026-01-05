"""
Job service for tracking background tasks.
"""

import uuid
from datetime import datetime
from typing import Dict, Optional
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStep(str, Enum):
    COLLECTING = "collecting"
    DOWNLOADING = "downloading"
    ANALYZING = "analyzing"
    TRAINING = "training"


class Job:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = JobStatus.PENDING
        self.current_step = None
        self.progress = 0
        self.total = 0
        self.message = ""
        self.error = None
        self.created_at = datetime.utcnow()
        self.completed_at = None
        self.result = None


from app.core.database import SessionLocal
from app.models.models import Job as JobModel

# In-memory job store is REMOVED in favor of database
# _jobs: Dict[str, Job] = {}

class JobDTO:
    """Data Transfer Object for Job model to decouple from DB session."""
    def __init__(self, model: JobModel):
        self.job_id = model.job_id
        self.status = JobStatus(model.status) if model.status else JobStatus.PENDING
        self.current_step = JobStep(model.current_step) if model.current_step else None
        self.progress = model.progress
        self.total = model.total
        self.message = model.message
        self.error = model.error
        self.created_at = model.created_at
        self.completed_at = model.completed_at
        self.result = model.result

def create_job() -> str:
    """Create a new job and return its ID."""
    job_id = str(uuid.uuid4())
    
    print(f"DEBUG: Creating job {job_id} in database...")
    db = SessionLocal()
    try:
        job = JobModel(job_id=job_id, status=JobStatus.PENDING.value)
        db.add(job)
        db.commit()
        print(f"DEBUG: Job {job_id} committed successfully.")
        return job_id
    except Exception as e:
        print(f"ERROR: Failed to create job {job_id}: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


def get_job(job_id: str) -> Optional[JobDTO]:
    """Get a job by ID."""
    db = SessionLocal()
    try:
        job = db.query(JobModel).filter(JobModel.job_id == job_id).first()
        if job:
            return JobDTO(job)
        return None
    except Exception as e:
        print(f"ERROR: Failed to get job {job_id}: {e}")
        return None
    finally:
        db.close()


def update_job(job_id: str, **kwargs):
    """Update job properties."""
    db = SessionLocal()
    try:
        job = db.query(JobModel).filter(JobModel.job_id == job_id).first()
        if job:
            for key, value in kwargs.items():
                if hasattr(job, key):
                    # Handle Enum conversion
                    if isinstance(value, Enum):
                        value = value.value
                    setattr(job, key, value)
            db.commit()
    except Exception as e:
        print(f"Error updating job {job_id}: {e}")
    finally:
        db.close()


def get_active_job() -> Optional[JobDTO]:
    """Get the most recent pending or running job."""
    db = SessionLocal()
    try:
        # Get the most recent job that is not completed, failed, or cancelled
        job = (
            db.query(JobModel)
            .filter(JobModel.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]))
            .order_by(JobModel.created_at.desc())
            .first()
        )
        if job:
            return JobDTO(job)
        return None
    except Exception as e:
        print(f"ERROR: Failed to get active job: {e}")
        return None
    finally:
        db.close()
