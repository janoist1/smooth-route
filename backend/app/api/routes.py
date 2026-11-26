"""REST surface kept next to GraphQL: the job-progress SSE stream only.

The React frontend follows a running job (route collection / analysis) over
Server-Sent Events: GET /api/v1/job/{job_id}/stream. Everything else is
GraphQL. The old REST endpoints (/api/v1/points, /points/{id},
/process-route, /job/{id}, /job/{id}/stop, /jobs/active) had no caller left
— the static map that used them is gone — and were removed (T-65).
Local only: the public read-only deploy does not mount this router.
"""
import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.services.job_service import JobStatus, get_job

router = APIRouter()


@router.get("/api/v1/job/{job_id}/stream")
async def stream_job_status(job_id: str):
    """Stream job status and progress using SSE."""

    async def event_generator():
        last_progress = -1
        last_status = None
        last_message = None

        while True:
            job = get_job(job_id)
            if not job:
                yield {"event": "error", "data": "Job not found"}
                break

            # Push on any visible change. `message` carries the fine-grained
            # counter (e.g. "876/1871"), which changes far more often than the
            # integer `progress` percentage — without it the client's progress
            # text looks frozen between whole-percent ticks.
            if (
                job.progress != last_progress
                or job.status != last_status
                or job.message != last_message
            ):
                last_progress = job.progress
                last_status = job.status
                last_message = job.message

                yield {
                    "data": json.dumps(
                        {
                            "job_id": job.job_id,
                            "status": job.status.value,
                            "current_step": job.current_step.value
                            if job.current_step
                            else None,
                            "progress": job.progress,
                            "total": job.total,
                            "message": job.message,
                            "error": job.error,
                            "result": job.result,
                        }
                    )
                }

            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break

            await asyncio.sleep(0.1)  # Faster heartbeat for rapid tasks

    return EventSourceResponse(event_generator())
