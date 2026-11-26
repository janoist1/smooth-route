"""Selected-route mutation validation and dispatch; no DB or paid calls."""
from types import SimpleNamespace

import pytest

from app.core.auth import Identity
from app.graphql.limits import MAX_PATH_POINTS
from app.graphql.schema import read_schema, schema

ADMIN = Identity(user_id="admin", clerk_id="admin", email=None, role="admin")
QUERY = "mutation($input: ProcessRouteInput!) { processRoute(input: $input) { id } }"


@pytest.fixture
def dispatch_job(monkeypatch):
    from app.graphql import mutations
    from app.services.job_runner import job_runner

    calls = []
    monkeypatch.setattr(mutations, "create_job", lambda: calls.append("create") or "job2")
    monkeypatch.setattr(job_runner, "run_background_task", lambda **kw: calls.append(kw))
    return calls


def execute(path, identity=ADMIN):
    return schema.execute_sync(
        QUERY, variable_values={"input": {"origin": "Budapest", "destination": "Budaörs", "path": path}},
        context_value={"identity": identity},
    )


def test_selected_alternative_is_passed_to_the_job(dispatch_job):
    from app.services.tasks import run_route_processing

    path = [[47.5, 19.05], [47.51, 19.07], [47.6, 19.10]]
    result = execute(path)
    assert result.errors is None
    assert result.data == {"processRoute": {"id": "job2"}}
    assert dispatch_job == ["create", {
        "target": run_route_processing,
        "args": ("job2", "Budapest", "Budaörs", [tuple(p) for p in path]),
    }]


@pytest.mark.parametrize("path", [
    [], [[47.5, 19.05]], [[47.5, 19.05, 1], [47.6, 19.1]],
    [[47.5, 19.05], [51.5, -0.1]], [[91, 19], [47.5, 19.05]],
    [[47.5, 19.05]] * (MAX_PATH_POINTS + 1),
    [[46, 17], [48, 22], [46, 17], [48, 22]],
])
def test_invalid_geometry_is_rejected_before_creating_a_job(path, dispatch_job):
    result = execute(path)
    assert result.errors
    assert result.errors[0].extensions["code"] == "BAD_USER_INPUT"
    assert dispatch_job == []


@pytest.mark.parametrize("identity", [None, SimpleNamespace(is_admin=False)])
def test_collection_requires_an_admin(identity, dispatch_job):
    result = execute([[47.5, 19.05], [47.6, 19.1]], identity)
    assert result.errors[0].extensions["code"] == "FORBIDDEN"
    assert dispatch_job == []


def test_collection_mutation_is_absent_from_public_schema():
    assert read_schema.get_type_by_name("Mutation") is None
