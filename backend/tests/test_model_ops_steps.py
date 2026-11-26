"""Admin model ops: the step runner behind retrain / model card / rescore.

The scripts themselves never run here: ``subprocess.Popen`` is a fake that
replays canned output lines and an exit code. No DB, no training, no torch."""
import sys
import types
from types import SimpleNamespace

import pytest

from app.services import job_runner, job_service
from app.services import model_ops as ops
from app.services.job_service import JobStatus, JobStep


class FakeProc:
    def __init__(self, lines, code):
        self.stdout = iter(lines)
        self.code = code

    def wait(self):
        return self.code


@pytest.fixture
def runner(monkeypatch):
    """Fake Popen + recorded job updates; the busy lock is free again afterwards."""
    rig = SimpleNamespace(updates=[], commands=[], outputs=[])

    def fake_popen(cmd, cwd=None, **kwargs):
        rig.commands.append((cmd, cwd))
        lines, code = rig.outputs.pop(0)
        return FakeProc(lines, code)

    monkeypatch.setattr(ops.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(job_service, "update_job", lambda job_id, **kw: rig.updates.append(kw))
    yield rig
    if ops._busy.locked():
        ops._busy.release()


def run_steps(steps, **kwargs):
    assert ops._busy.acquire(blocking=False)            # what _start does before the thread
    ops._run_steps("job1", steps, **kwargs)


def test_finished_steps_complete_the_job_with_the_scripts_last_word(runner):
    runner.outputs = [(["[retrain] export labels\n", "\n", "[retrain] gate: PASS\n"], 0)]
    run_steps([("Újratanítás", ["python", "ml/retrain.py"], "/repo")],
              progress=ops.retrain_progress, on_done=lambda: {"summary": "ok"})

    assert runner.commands == [(["python", "ml/retrain.py"], "/repo")]
    first, done = runner.updates[0], runner.updates[-1]
    assert first["status"] is JobStatus.RUNNING and first["current_step"] is JobStep.TRAINING
    assert (first["progress"], first["total"], first["message"]) == (0, 100, "Újratanítás")
    lines = [kw["message"] for kw in runner.updates[1:-1]]
    assert lines == ["Újratanítás: [retrain] export labels", "Újratanítás: [retrain] gate: PASS"]
    progress = [kw["progress"] for kw in runner.updates[1:-1]]
    assert progress == sorted(progress) and progress[-1] > 0     # monotonic, blank line skipped
    assert done["status"] is JobStatus.COMPLETED and done["progress"] == 100
    assert done["message"] == "Kész — [retrain] gate: PASS"
    assert done["result"] == {"summary": "ok"} and done["completed_at"] is not None
    assert not ops._busy.locked()


def test_silent_script_completes_with_a_plain_done_and_an_empty_result(runner):
    runner.outputs = [([], 0)]
    run_steps([("Modellkártya", ["python", "card.py"], "/repo")])
    done = runner.updates[-1]
    assert done["message"] == "Kész" and done["result"] == {}


def test_failing_step_fails_the_job_and_skips_the_rest(runner):
    runner.outputs = [(["scoring…\n", "Traceback: model missing\n"], 1), ([], 0)]
    called = []
    run_steps([("Újrapontozás", ["python", "rescore.py"], "/b"),
               ("Szakaszok", ["python", "build.py"], "/b")], on_done=lambda: called.append(1))

    assert len(runner.commands) == 1 and called == []   # second step never started
    last = runner.updates[-1]
    assert last["status"] is JobStatus.FAILED
    assert last["error"] == "Újrapontozás failed: Traceback: model missing"
    assert last["message"] == "Újrapontozás: hiba"
    assert not ops._busy.locked()                       # a failed run does not block the next


def test_later_steps_start_at_the_progress_reached_so_far(runner):
    runner.outputs = [(["a\n"], 0), (["b\n"], 0)]
    run_steps([("One", ["x"], "/"), ("Two", ["y"], "/")], progress=lambda line, cur: cur + 40)
    starts = [kw["progress"] for kw in runner.updates if kw.get("message") in ("One", "Two")]
    assert starts == [0, 40]


def test_only_one_model_job_runs_at_a_time(runner, monkeypatch):
    started = []
    monkeypatch.setattr(job_service, "create_job", lambda: "job-9")
    monkeypatch.setattr(job_runner.job_runner, "run_threaded_task",
                        lambda fn, args: started.append((fn, args)))

    assert ops._start([("One", ["x"], "/")]) == "job-9"
    (fn, args), = started
    assert fn is ops._run_steps and args[0] == "job-9" and args[1] == [("One", ["x"], "/")]
    with pytest.raises(ops.PromotionError, match="Már fut"):
        ops._start([("Two", ["y"], "/")])               # the first has not finished yet
    assert len(started) == 1


def test_the_three_admin_jobs_run_the_expected_scripts(monkeypatch):
    seen = []

    def fake_start(steps, progress=None, on_done=None):
        seen.append((steps, progress, on_done))
        return f"job-{len(seen)}"

    monkeypatch.setattr(ops, "_start", fake_start)
    monkeypatch.setattr(ops, "latest_summary", lambda: {"verdict": True})

    assert ops.start_retrain() == "job-1"
    steps, progress, on_done = seen[0]
    assert [(cmd, cwd) for _, cmd, cwd in steps] == [([sys.executable, "ml/retrain.py"], ops.ROOT)]
    assert progress is ops.retrain_progress
    assert on_done() == {"summary": {"verdict": True}}

    assert ops.start_model_card() == "job-2"
    assert seen[1][0][0][1] == [sys.executable, "ml/build_model_card.py"]

    assert ops.start_rescore_and_rebuild() == "job-3"
    commands = [(cmd[1:], cwd) for _, cmd, cwd in seen[2][0]]
    backend = ops.os.path.join(ops.ROOT, "backend")
    assert commands == [(["scripts/rescore_dino.py"], backend),
                        (["scripts/build_segments.py", "--offline"], backend)]


def test_reload_marks_the_live_model_for_loading_again(monkeypatch):
    fake = types.ModuleType("app.services.dino_service")
    fake.dino_service = SimpleNamespace(_loaded=True)
    monkeypatch.setitem(sys.modules, "app.services.dino_service", fake)
    ops.reload_live_model()
    assert fake.dino_service._loaded is False


def test_champion_training_set_reads_the_manifest_filenames(tmp_path):
    manifest = tmp_path / "dataset_v2.csv"
    manifest.write_text("image_filename,rqi\nsv_1.jpg,2\nsv_2.jpg,4\nsv_1.jpg,2\n", encoding="utf-8")
    assert ops.champion_training_set(str(manifest)) == {"sv_1.jpg", "sv_2.jpg"}
    assert ops.champion_training_set(str(tmp_path / "missing.csv")) == set()


def test_retrain_line_without_a_known_step_keeps_the_progress():
    assert ops.retrain_progress("[retrain] zzz", 40) == 40
