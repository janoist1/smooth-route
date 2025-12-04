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

class JobStep(str, Enum):
    COLLECTING = "collecting"
    DOWNLOADING = "downloading"
    ANALYZING = "analyzing"

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

# In-memory job store (in production, use Redis or database)
_jobs: Dict[str, Job] = {}

def create_job() -> str:
    """Create a new job and return its ID."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = Job(job_id)
    return job_id

def get_job(job_id: str) -> Optional[Job]:
    """Get a job by ID."""
    return _jobs.get(job_id)

def update_job(job_id: str, **kwargs):
    """Update job properties."""
    job = _jobs.get(job_id)
    if job:
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

