"""Contract tests for the intentionally retained REST surface."""

from app.api.routes import router


def test_duplicate_rest_inference_endpoint_is_removed():
    paths = {route.path for route in router.routes}

    assert "/api/v1/inference/detect" not in paths


def test_rest_endpoints_needed_by_static_ui_and_sse_remain():
    paths = {route.path for route in router.routes}

    assert {
        "/api/v1/config",
        "/api/v1/points",
        "/api/v1/points/{point_id}",
        "/api/v1/process-route",
        "/api/v1/job/{job_id}",
        "/api/v1/job/{job_id}/stream",
    } <= paths
