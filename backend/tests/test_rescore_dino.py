"""Pure helpers of scripts/rescore_dino.py (no torch, no DB).

Loading the script module here also proves it stays importable without torch
(CI has none): the model is only imported inside main().
"""
import csv
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "rescore_dino", Path(__file__).resolve().parents[1] / "scripts" / "rescore_dino.py"
)
rescore = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rescore)


def test_artifact_id_follows_the_file_content(tmp_path):
    a = tmp_path / "a.joblib"
    a.write_bytes(b"model v2")
    b = tmp_path / "b.joblib"
    b.write_bytes(b"model v2")
    c = tmp_path / "c.joblib"
    c.write_bytes(b"model v3")
    assert rescore.artifact_id(a) == rescore.artifact_id(b)
    assert rescore.artifact_id(a) != rescore.artifact_id(c)
    assert len(rescore.artifact_id(a)) == 12


def test_resume_marker():
    assert rescore.is_done("2.61", "abc123", "abc123")
    assert not rescore.is_done("2.61", None, "abc123")          # scored before the marker existed
    assert not rescore.is_done("2.61", "old000", "abc123")      # scored by another artifact
    assert not rescore.is_done(None, "abc123", "abc123")        # marker without a score


def test_metadata_patch_matches_the_product_keys():
    patch = rescore.metadata_patch(2.71828, 0.61234, "abc123", 2, "2026-11-26 12:00:00")
    assert patch == {
        "dino_strategy": "DINO Classification",
        "dino_score": 2.718,
        "dino_p_bad": 0.612,
        "dino_timestamp": "2026-11-26 12:00:00",
        "dino_artifact": "abc123",
        "dino_model_version": 2,
    }
    # No calibrator in the artifact → the key is simply absent.
    assert "dino_p_bad" not in rescore.metadata_patch(2.0, None, "abc123", 2, "t")
    # The previous class is NOT part of the patch: it is preserved in SQL,
    # only when the key does not exist yet.
    assert "dino_rqi_score_prev" not in patch
    assert "jsonb_exists" in rescore.UPDATE_SQL and "dino_rqi_score_prev" in rescore.UPDATE_SQL


def test_shift_table_counts_old_to_new():
    pairs = [(2.0, 2), (2.0, 2), (2.0, 3), (3.0, 3), (3.0, 4), ("", 1), (None, 1)]
    lines = rescore.shift_table(pairs)
    assert lines[0].split() == ["old", "\\", "new", "1", "2", "3", "4", "total"]
    by_old = {line.split()[0]: [int(x) for x in line.split()[1:]] for line in lines[1:-1]}
    assert by_old["-"] == [2, 0, 0, 0, 2]          # frames that had no class before
    assert by_old["2"] == [0, 2, 1, 0, 3]
    assert by_old["3"] == [0, 0, 1, 1, 2]
    assert lines[-1] == "unchanged: 3/7 (42.9 %)"
    assert rescore.shift_table([]) == ["(no frames)"]


def test_read_log_keeps_the_original_old_value_and_the_latest_new_one(tmp_path):
    path = tmp_path / "log.csv"
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rescore.LOG_FIELDS)
        writer.writeheader()
        writer.writerow({"id": 1, "old_rqi": 3.0, "old_score": "", "new_score": 2.4, "new_rqi": 2, "new_p_bad": 0.3})
        writer.writerow({"id": 2, "old_rqi": 2.0, "old_score": 2.1, "new_score": 2.1, "new_rqi": 2, "new_p_bad": 0.2})
        # a later --force run over frame 1: its "old" is now the re-scored value
        writer.writerow({"id": 1, "old_rqi": 2.0, "old_score": 2.4, "new_score": 2.5, "new_rqi": 3, "new_p_bad": 0.5})
    rows = {r["id"]: r for r in rescore.read_log(path)}
    assert set(rows) == {"1", "2"}
    assert (rows["1"]["old_rqi"], rows["1"]["new_rqi"]) == ("3.0", "3")     # original → latest
    assert rows["1"]["old_score"] == ""
    assert rescore.read_log(tmp_path / "missing.csv") == []


@pytest.mark.parametrize("value, label", [(2.0, "2"), ("3.0", "3"), (2.5, "2.5"), (None, "-"), ("", "-")])
def test_class_labels(value, label):
    assert rescore._class_label(value) == label


# --- feature vectors --------------------------------------------------------

def test_merge_features_new_wins():
    old = {1: ("a", True), 2: ("b", True)}
    assert rescore.merge_features(old, {2: ("B", False), 3: ("c", True)}) == {
        1: ("a", True), 2: ("B", False), 3: ("c", True)}
    assert rescore.merge_features(None, {5: ("x", True)}) == {5: ("x", True)}
    assert old == {1: ("a", True), 2: ("b", True)}          # input untouched


def test_save_features_round_trip_merge_and_artifact_change(tmp_path):
    np = pytest.importorskip("numpy")
    path = tmp_path / "cache" / "frame_feats.npz"
    first = {3: (np.ones(4, dtype="float32"), False), 1: (np.arange(4, dtype="float32"), True)}
    assert rescore.save_features(path, first, "art1", "cls+patch", ["cls", "patch"]) == 2

    with np.load(path) as data:
        assert data["ids"].tolist() == [1, 3]                       # sorted by id
        assert data["ids"].dtype == np.int32
        assert data["feats"].shape == (2, 4) and data["feats"].dtype == np.float16
        assert data["feats"][0].tolist() == [0.0, 1.0, 2.0, 3.0]
        assert data["usable"].tolist() == [True, False]
        assert (str(data["artifact"]), str(data["recipe"])) == ("art1", "cls+patch")
        assert data["keys"].tolist() == ["cls", "patch"]

    # Same artifact: update frame 3, add frame 2, keep frame 1.
    more = {3: (np.zeros(4), True), 2: (np.full(4, 2.0), True)}
    assert rescore.save_features(path, more, "art1", "cls+patch", ["cls", "patch"]) == 3
    with np.load(path) as data:
        assert data["ids"].tolist() == [1, 2, 3]
        assert data["feats"][2].tolist() == [0.0] * 4
        assert data["usable"].tolist() == [True, True, True]

    # Another artifact: its vectors are not comparable → the file is replaced.
    assert rescore.save_features(path, {9: (np.ones(4), True)}, "art2", "cls", ["cls"]) == 1
    with np.load(path) as data:
        assert data["ids"].tolist() == [9] and str(data["artifact"]) == "art2"
    assert not list(path.parent.glob("*.tmp*"))                      # atomic write
