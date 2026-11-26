"""job_service against a fake session: job rows in, DTOs out, no database."""
import uuid
from types import SimpleNamespace

import pytest

from app.services import job_service as js
from app.services.job_service import Job, JobDTO, JobStatus, JobStep


class FakeQuery:
    def __init__(self, session):
        self.session = session

    def filter(self, *criteria):
        self.session.calls.append("filter")
        return self

    def order_by(self, *criteria):
        self.session.calls.append("order_by")
        return self

    def first(self):
        if self.session.query_error:
            raise self.session.query_error
        return self.session.row


class FakeSession:
    def __init__(self, row=None, query_error=None, commit_error=None):
        self.row = row
        self.query_error = query_error
        self.commit_error = commit_error
        self.calls = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, model):
        return FakeQuery(self)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        if self.commit_error:
            raise self.commit_error
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def use_session(monkeypatch, **kwargs) -> FakeSession:
    session = FakeSession(**kwargs)
    monkeypatch.setattr(js, "SessionLocal", lambda: session)
    return session


def job_row(**overrides):
    row = dict(job_id="j1", status="running", current_step="analyzing", progress=3, total=10,
               message="working", error=None, created_at="t0", completed_at=None, result=None)
    row.update(overrides)
    return SimpleNamespace(**row)


def test_new_in_memory_job_starts_pending_and_empty():
    job = Job("abc")
    assert job.job_id == "abc" and job.status is JobStatus.PENDING
    assert (job.progress, job.total, job.message) == (0, 0, "")
    assert job.current_step is None and job.error is None and job.result is None
    assert job.created_at is not None and job.completed_at is None


def test_dto_turns_stored_strings_into_enums():
    dto = JobDTO(job_row(result={"saved": 2}))
    assert dto.status is JobStatus.RUNNING and dto.current_step is JobStep.ANALYZING
    assert (dto.job_id, dto.progress, dto.total, dto.message) == ("j1", 3, 10, "working")
    assert dto.result == {"saved": 2} and dto.created_at == "t0"


def test_dto_defaults_for_a_row_without_status_or_step():
    dto = JobDTO(job_row(status=None, current_step=None))
    assert dto.status is JobStatus.PENDING and dto.current_step is None


def test_dto_rejects_an_unknown_status():
    with pytest.raises(ValueError):
        JobDTO(job_row(status="exploded"))


def test_create_job_stores_a_pending_row_and_returns_its_uuid(monkeypatch):
    session = use_session(monkeypatch)
    job_id = js.create_job()
    assert str(uuid.UUID(job_id)) == job_id
    (row,) = session.added
    assert row.job_id == job_id and row.status == "pending"
    assert session.commits == 1 and session.rollbacks == 0 and session.closed


def test_create_job_rolls_back_and_reraises_when_the_commit_fails(monkeypatch):
    session = use_session(monkeypatch, commit_error=RuntimeError("db down"))
    with pytest.raises(RuntimeError, match="db down"):
        js.create_job()
    assert session.rollbacks == 1 and session.closed


def test_get_job_returns_a_dto_or_none(monkeypatch):
    session = use_session(monkeypatch, row=job_row(job_id="j7", status="completed"))
    dto = js.get_job("j7")
    assert dto.job_id == "j7" and dto.status is JobStatus.COMPLETED and session.closed

    missing = use_session(monkeypatch, row=None)
    assert js.get_job("nope") is None and missing.closed


def test_get_job_swallows_a_query_error(monkeypatch):
    session = use_session(monkeypatch, query_error=RuntimeError("boom"))
    assert js.get_job("j1") is None
    assert session.closed


def test_update_job_sets_known_fields_and_stores_enum_values(monkeypatch):
    row = job_row(status="pending", current_step=None, progress=0)
    session = use_session(monkeypatch, row=row)
    js.update_job("j1", status=JobStatus.RUNNING, current_step=JobStep.DOWNLOADING,
                  progress=40, message="half way", not_a_column="ignored")
    assert row.status == "running" and row.current_step == "downloading"
    assert row.progress == 40 and row.message == "half way"
    assert not hasattr(row, "not_a_column")
    assert session.commits == 1 and session.closed


def test_update_job_for_an_unknown_job_commits_nothing(monkeypatch):
    session = use_session(monkeypatch, row=None)
    js.update_job("ghost", progress=5)
    assert session.commits == 0 and session.closed


def test_update_job_never_raises(monkeypatch):
    session = use_session(monkeypatch, row=job_row(), commit_error=RuntimeError("db down"))
    js.update_job("j1", progress=5)          # logged, not raised: progress is best-effort
    assert session.closed


def test_get_active_job_is_the_newest_pending_or_running_one(monkeypatch):
    session = use_session(monkeypatch, row=job_row(status="pending"))
    dto = js.get_active_job()
    assert dto.status is JobStatus.PENDING
    assert session.calls == ["filter", "order_by"] and session.closed

    idle = use_session(monkeypatch, row=None)
    assert js.get_active_job() is None and idle.closed


def test_get_active_job_swallows_a_query_error(monkeypatch):
    session = use_session(monkeypatch, query_error=RuntimeError("boom"))
    assert js.get_active_job() is None
    assert session.closed
