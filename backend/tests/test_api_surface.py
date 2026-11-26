"""Contract tests for the intentionally retained REST surface."""

from app.api.routes import router


def test_only_the_job_progress_stream_remains():
    # The frontend follows jobs over SSE; everything else is GraphQL. The old
    # REST routes had no caller (T-65) and must not come back unnoticed.
    paths = {route.path for route in router.routes}
    assert paths == {"/api/v1/job/{job_id}/stream"}


def test_removed_routes_stay_removed():
    paths = {route.path for route in router.routes}
    for gone in ("/api/v1/inference/detect", "/api/v1/config", "/api/v1/points",
                 "/api/v1/points/{point_id}", "/api/v1/process-route", "/api/v1/job/{job_id}",
                 "/api/v1/job/{job_id}/stop", "/api/v1/jobs/active"):
        assert gone not in paths
