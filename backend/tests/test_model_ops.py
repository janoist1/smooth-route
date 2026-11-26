"""Admin model ops (T-68): pure parts only — no DB, no training, no torch."""
import json
import os

import pytest

from app.services import model_ops as ops


def test_retrain_progress_is_monotonic_and_ignores_other_lines():
    p = 0
    for line, want in [("[retrain] export labels", 10), ("noise 99%", 10), ("[retrain] features", 30),
                       ("[retrain] export again", 30), ("[retrain] gate", 75)]:
        p = ops.retrain_progress(line, p)
        assert p == want


def test_report_in_plain_hungarian():
    s = {"verdict": False, "gate_pass": True, "why": "new labels do not help",
         "paired_old_vs_all": {"qwk": [-0.01, -0.03, 0.01]},
         "candidate_cv": {"qwk": 0.781, "mae": 0.39},
         "budapest_candidate_oof": {"qwk": 0.61}, "leave_budapest_out": {"qwk": 0.42}}
    text = "\n".join(ops.describe_report(s))
    assert "NE élesítsd" in text and "MEGFELELT (PASS)" in text
    assert "ΔQWK -0.010 (95% CI -0.030 … +0.010)" in text
    assert "Budapest: QWK 0.610" in text and "új terület" in text
    assert ops.describe_report(None) == ["Még nem futott újratanítás."]


def test_latest_summary_picks_the_newest_run(tmp_path):
    for i, name in enumerate(["20261126T1000", "20261126T1100"]):
        d = tmp_path / name
        d.mkdir()
        (d / "summary.json").write_text(json.dumps({"verdict": bool(i)}))
        os.utime(d / "summary.json", (1_000 + i, 1_000 + i))
    assert ops.latest_summary(str(tmp_path))["verdict"] is True
    assert ops.latest_summary(str(tmp_path / "none")) is None


def test_promotion_needs_the_phrase_a_candidate_and_a_pass(tmp_path):
    champ, cand = tmp_path / "rqi_model.joblib", tmp_path / "rqi_model_candidate.joblib"
    champ.write_bytes(b"old")
    kw = dict(champion=str(champ), candidate=str(cand))
    with pytest.raises(ops.PromotionError):
        ops.promote("igen", **kw)                       # wrong phrase
    with pytest.raises(ops.PromotionError):
        ops.promote(ops.CONFIRM_PHRASE, **kw)           # no candidate
    cand.write_bytes(b"new")
    with pytest.raises(ops.PromotionError):
        ops.promote(ops.CONFIRM_PHRASE, summary={"gate_pass": False}, **kw)
    backup = ops.promote(ops.CONFIRM_PHRASE, summary={"gate_pass": True}, **kw)
    assert champ.read_bytes() == b"new" and open(backup, "rb").read() == b"old"
    assert os.path.basename(backup).startswith("rqi_model.") and backup.endswith(".bak.joblib")


def test_new_labels_exclude_the_champions_training_set():
    rows = [("a.jpg", 5.0, 47.5, 19.07), ("b.jpg", 2.0, 47.5, 19.07), ("c.jpg", 2.5, None, None)]
    n, by_area, by_level = ops.summarize_new_labels(
        rows, {"a.jpg"}, nearest=lambda x: round(x), area_of=lambda lat, lon: "budapest")
    assert n == 2 and by_area == {"budapest": 1, "other": 1} and sum(by_level.values()) == 2
    assert "998" in ops.learning_curve_hint(2) and "elérted" in ops.learning_curve_hint(1000)


@pytest.mark.parametrize("query", ["{ modelAdmin { newLabels } }", "mutation { startRetrain }",
                                   'mutation { promoteCandidate(confirm: "x") }',
                                   "mutation { startRescoreAndRebuild }"])
def test_admin_only(query):
    from app.core.auth import Identity
    from app.graphql.schema import schema

    user = Identity(user_id="u", clerk_id="u", email=None, role="user")
    for identity in (None, user):
        res = schema.execute_sync(query, context_value={"identity": identity})
        assert res.data is None and "Admin privileges required" in res.errors[0].message
