"""Admin model operations without a terminal (T-68).

- label progress since the champion was trained (by area, by level), sprint
  progress and the learning-curve hint;
- "Újratanítás és mérés": runs ml/retrain.py (== `make retrain`) as a job and
  reports its spatial gate verdict in plain Hungarian (ml/cache/retrain/<run>/
  summary.json, written by retrain.py);
- "Élesítés": promotes ml/cache/rqi_model_candidate.joblib only after an
  explicit confirmation phrase, keeping a timestamped backup of the champion,
  then regenerates ml/model_card.json; re-score + segment rebuild is a separate
  follow-up job.

The pure parts (progress percent, report text, promotion file ops) are
unit-tested; the job wrappers only run the existing scripts.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE = os.path.join(ROOT, "ml", "cache")
CHAMPION = os.path.join(CACHE, "rqi_model.joblib")
CANDIDATE = os.path.join(CACHE, "rqi_model_candidate.joblib")
MANIFEST = os.path.join(CACHE, "dataset_v2.csv")  # the champion's training set
RETRAIN_RUNS = os.path.join(CACHE, "retrain")
CONFIRM_PHRASE = "ÉLESÍTÉS"
LEARNING_CURVE_TARGET = 1000

# --- progress -----------------------------------------------------------------

# retrain.py prints "[retrain] <step> ..." lines; each step start -> percent.
RETRAIN_STEPS = [("export", 10), ("feature", 30), ("coord", 45), ("fit", 60),
                 ("gate", 75), ("report", 90), ("paired", 90), ("summary", 97)]


def retrain_progress(line: str, current: int) -> int:
    """Monotonic percent from one output line of retrain.py."""
    low = line.lower()
    if not low.startswith("[retrain]"):
        return current
    for key, pct in RETRAIN_STEPS:
        if key in low:
            return max(current, pct)
    return current


def learning_curve_hint(new_labels: int, target: int = LEARNING_CURVE_TARGET) -> str:
    left = max(0, target - new_labels)
    if left == 0:
        return (f"{new_labels} új címke: elérted a tanulási görbe szerinti ~{target}-et. "
                "Érdemes újratanítani és mérni.")
    return (f"{new_labels} új címke a bajnok modell óta. A tanulási görbe szerint ~{target} új "
            f"címke új utcákon kb. +0,02–0,04 QWK-t hoz; még kb. {left} van hátra.")


# --- report -------------------------------------------------------------------

def latest_summary(runs_dir: str = RETRAIN_RUNS) -> Optional[dict]:
    """Newest ml/cache/retrain/<run>/summary.json, with its run dir."""
    paths = sorted(glob.glob(os.path.join(runs_dir, "*", "summary.json")), key=os.path.getmtime)
    if not paths:
        return None
    with open(paths[-1], encoding="utf-8") as fh:
        data = json.load(fh)
    data["_run_dir"] = os.path.relpath(os.path.dirname(paths[-1]), ROOT)
    data["_at"] = datetime.fromtimestamp(os.path.getmtime(paths[-1])).strftime("%Y-%m-%d %H:%M")
    return data


def _metric(m: Optional[dict], key: str) -> Optional[float]:
    if not isinstance(m, dict) or m.get(key) is None:
        return None
    try:
        return float(m[key])
    except (TypeError, ValueError):
        return None


def describe_report(s: Optional[dict]) -> list[str]:
    """retrain.py summary.json -> short Hungarian lines for the admin panel."""
    if not s:
        return ["Még nem futott újratanítás."]
    lines = []
    lines.append("Javaslat: ÉLESÍTHETŐ." if s.get("verdict") else "Javaslat: NE élesítsd.")
    lines.append("Térbeli kapu (bajnok számaihoz mérve): "
                 + ("MEGFELELT (PASS)." if s.get("gate_pass") else "NEM FELELT MEG (FAIL)."))
    paired = s.get("paired_old_vs_all")
    if isinstance(paired, dict) and isinstance(paired.get("qwk"), (list, tuple)) and len(paired["qwk"]) == 3:
        d, lo, hi = (float(x) for x in paired["qwk"])
        lines.append(f"Az új címkék hatása (páros teszt): ΔQWK {d:+.3f} "
                     f"(95% CI {lo:+.3f} … {hi:+.3f}).")
    cand = s.get("candidate_cv")
    q = _metric(cand, "qwk")
    if q is not None:
        mae = _metric(cand, "mae")
        lines.append(f"Jelölt, térbeli CV: QWK {q:.3f}" + (f", MAE {mae:.3f}." if mae is not None else "."))
    for key, label in (("budapest_candidate_oof", "Budapest"),
                       ("leave_budapest_out", "Budapest kihagyva tanításból (új terület)"),
                       ("new_labels_champion", "Új címkéken a régi bajnok"),
                       ("new_labels_candidate_oof", "Új címkéken a jelölt")):
        q = _metric(s.get(key), "qwk")
        if q is not None:
            lines.append(f"{label}: QWK {q:.3f}.")
    why = s.get("why")
    if why:
        lines.append(f"Indoklás: {why}")
    return lines


# --- promotion ------------------------------------------------------------------

class PromotionError(ValueError):
    pass


def promote(confirm: str, *, champion: str = CHAMPION, candidate: str = CANDIDATE,
            summary: Optional[dict] = None, now: Optional[datetime] = None) -> str:
    """Swap the candidate in; returns the backup path. Refuses without the exact
    confirmation phrase, without a candidate, or when the gate did not pass."""
    if (confirm or "").strip() != CONFIRM_PHRASE:
        raise PromotionError(f'Írd be pontosan: "{CONFIRM_PHRASE}"')
    if not os.path.isfile(candidate):
        raise PromotionError("Nincs jelölt modell (előbb: Újratanítás és mérés).")
    if summary is not None and not summary.get("gate_pass"):
        raise PromotionError("A jelölt nem ment át a térbeli kapun: nem élesíthető.")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    backup = os.path.join(os.path.dirname(champion), f"rqi_model.{stamp}.bak.joblib")
    if os.path.isfile(champion):
        shutil.copy2(champion, backup)
    tmp = champion + ".tmp"
    shutil.copy2(candidate, tmp)
    os.replace(tmp, champion)  # atomic: the service never sees half a file
    return backup


# --- jobs (thin wrappers around the existing scripts) ----------------------------

_busy = threading.Lock()


def _run_steps(job_id: str, steps: Iterable[tuple[str, list[str], str]],
               progress: Callable[[str, int], int] = lambda line, cur: cur,
               on_done: Optional[Callable[[], dict]] = None) -> None:
    from app.services.job_service import JobStatus, JobStep, update_job

    pct = 0
    last = ""
    try:
        for title, cmd, cwd in steps:
            update_job(job_id, status=JobStatus.RUNNING, current_step=JobStep.TRAINING,
                       progress=pct, total=100, message=title)
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.rstrip()
                if not line:
                    continue
                last = line
                pct = progress(line, pct)
                update_job(job_id, progress=pct, message=f"{title}: {line[:160]}")
            if proc.wait() != 0:
                update_job(job_id, status=JobStatus.FAILED, error=f"{title} failed: {last[:300]}",
                           message=f"{title}: hiba")
                return
        result = on_done() if on_done else {}
        # Keep the script's last word ("only 6 new labels … nothing to do").
        update_job(job_id, status=JobStatus.COMPLETED, progress=100,
                   message=f"Kész — {last[:200]}" if last else "Kész", result=result,
                   completed_at=datetime.now(timezone.utc).replace(tzinfo=None))
    except Exception as exc:  # pragma: no cover - defensive
        update_job(job_id, status=JobStatus.FAILED, error=str(exc)[:300])
    finally:
        _busy.release()


def _start(steps, progress=lambda line, cur: cur, on_done=None) -> str:
    from app.services.job_runner import job_runner
    from app.services.job_service import create_job

    if not _busy.acquire(blocking=False):
        raise PromotionError("Már fut egy modell-feladat; várd meg a végét.")
    job_id = create_job()
    job_runner.run_threaded_task(_run_steps, (job_id, steps, progress, on_done))
    return job_id


def start_retrain() -> str:
    """ml/retrain.py (== make retrain): export -> features -> fit -> spatial gate."""
    return _start([("Újratanítás és mérés", [sys.executable, "ml/retrain.py"], ROOT)],
                  progress=retrain_progress,
                  on_done=lambda: {"summary": latest_summary()})


def start_model_card() -> str:
    return _start([("Modellkártya frissítése", [sys.executable, "ml/build_model_card.py"], ROOT)])


def start_rescore_and_rebuild() -> str:
    """Re-score frames with the live model, then rebuild the road segments."""
    backend = os.path.join(ROOT, "backend")
    return _start([
        ("Képek újrapontozása", [sys.executable, "scripts/rescore_dino.py"], backend),
        ("Útszakaszok újraépítése", [sys.executable, "scripts/build_segments.py", "--offline"], backend),
    ])


def reload_live_model() -> None:
    """Make the running service load the new champion on next use."""
    try:
        from app.services.dino_service import dino_service

        dino_service._loaded = False
    except Exception:  # pragma: no cover - torch-free deploys
        pass


# --- label progress ----------------------------------------------------------------

def champion_training_set(path: str = MANIFEST) -> set[str]:
    try:
        import csv

        with open(path, encoding="utf-8") as fh:
            return {r["image_filename"] for r in csv.DictReader(fh)}
    except OSError:
        return set()


def summarize_new_labels(rows: Iterable[tuple[str, float, float, float]], trained: set[str],
                         nearest: Callable[[float], int], area_of: Callable[[float, float], str]
                         ) -> tuple[int, dict[str, int], dict[int, int]]:
    """rows = (filename, manual_rqi, lat, lon). New = not in the champion's set."""
    n, by_area, by_level = 0, {}, {}
    for name, rqi, lat, lon in rows:
        if name in trained or rqi is None:
            continue
        n += 1
        area = area_of(lat, lon) if lat is not None and lon is not None else "other"
        by_area[area] = by_area.get(area, 0) + 1
        level = int(nearest(float(rqi)))
        by_level[level] = by_level.get(level, 0) + 1
    return n, by_area, by_level
