"""Public job progress without stored messages, errors, or result payloads."""
import datetime
from typing import Optional

import strawberry

from app.services import job_service


@strawberry.type
class PublicJob:
    id: str
    status: str
    progress: int
    total: int
    message: str
    created_at: datetime.datetime
    completed_at: Optional[datetime.datetime]


_MESSAGES = {
    "pending": "Job pending.",
    "running": "Job running.",
    "completed": "Job completed.",
    "failed": "Job failed.",
    "cancelled": "Job cancelled.",
}


def _public_job(job) -> Optional[PublicJob]:
    if job is None:
        return None
    status = job.status.value
    if status not in _MESSAGES:
        status = "unknown"
    return PublicJob(
        id=job.job_id, status=status, progress=job.progress or 0, total=job.total or 0,
        message=_MESSAGES.get(status, "Job status unavailable."),
        created_at=job.created_at, completed_at=job.completed_at,
    )


@strawberry.type
class PublicJobQuery:
    @strawberry.field
    def job(self, id: str) -> Optional[PublicJob]:
        return _public_job(job_service.get_job(id))

    @strawberry.field
    def active_job(self) -> Optional[PublicJob]:
        return _public_job(job_service.get_active_job())
