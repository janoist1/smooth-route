"""Tests for the pure parts of ml/frame_quality.py (no torch, no DB).

Run: .venv/bin/python -m pytest -q ml/tests/test_frame_quality.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import frame_quality as fq  # noqa: E402


def test_import_does_not_pull_torch_api():
    # The module itself must not import torch / transformers at import time.
    src = open(fq.__file__).read()
    head = src.split("def ensure_cache")[0]
    assert "import torch" not in head and "transformers" not in head


# --- heading -----------------------------------------------------------------
def test_heading_diff_circular():
    assert fq.heading_diff(350, 10) == 20
    assert fq.heading_diff(10, 350) == 20
    assert fq.heading_diff(0, 180) == 180
    assert fq.heading_diff(90, 90) == 0
    assert fq.heading_diff(725, 5) == 0
    np.testing.assert_allclose(fq.heading_diff([0, 359, 45], [270, 1, 46]), [90, 2, 1])


def test_haversine():
    d = fq.haversine_m(47.0, 19.0, 47.0 + 1 / 111_195, 19.0)
    assert abs(float(d) - 1.0) < 0.01


# --- hashes ------------------------------------------------------------------
def _scene(seed):
    rng = np.random.default_rng(seed)
    img = cv2_blur(rng.integers(0, 255, (378, 600)).astype(np.uint8))
    return img


def cv2_blur(a):
    import cv2
    return cv2.GaussianBlur(a, (0, 0), 25)


def test_phash_dhash_hamming():
    a = _scene(1)
    noisy = np.clip(a.astype(int) + np.random.default_rng(9).integers(-3, 4, a.shape), 0, 255).astype(np.uint8)
    b = _scene(2)
    for h in (fq.phash, fq.dhash):
        ha, hn, hb = h(a), h(noisy), h(b)
        assert 0 <= ha < 2 ** 64
        assert fq.hamming(ha, ha) == 0
        assert fq.hamming(ha, hn) <= 6          # near-identical image
        assert fq.hamming(ha, hb) >= 16         # different image
    assert fq.hamming(0, 2 ** 64 - 1) == 64
    assert fq.hamming(0b1011, 0b0001) == 2
    np.testing.assert_array_equal(
        fq.hamming(np.array([0, 3], np.uint64), np.array([1, 0], np.uint64)), [1, 2])


def test_image_features_placeholder_and_logo_strip():
    import cv2
    gray = np.full((400, 600, 3), 228, np.uint8)
    gray[380:] = 0                               # junk only inside the logo strip
    f = fq.image_features(gray)
    assert f["no_imagery"] and f["contrast"] == 0 and f["dark_frac"] == 0
    assert len(f["phash"]) == 16 and len(f["dhash"]) == 16

    rng = np.random.default_rng(0)
    sharp = rng.integers(0, 255, (400, 600, 3)).astype(np.uint8)
    soft = cv2.GaussianBlur(sharp, (0, 0), 6)
    fs, fb = fq.image_features(sharp), fq.image_features(soft)
    assert not fs["no_imagery"]
    assert fs["sharp_p90"] > 50 * fb["sharp_p90"]
    assert fs["blur_full"] > 50 * fb["blur_full"]


# --- duplicates --------------------------------------------------------------
M = 1 / 111_195  # one metre in degrees of latitude


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def _emb_like(e, cos, seed):
    """A unit vector with the given cosine to e."""
    r = np.random.default_rng(seed).normal(size=e.shape).astype(np.float32)
    r = _unit(r - (r @ e) * e)
    return _unit(cos * e + np.sqrt(1 - cos ** 2) * r)


def _frames():
    base = int(fq.phash(_scene(1)))
    other = int(fq.phash(_scene(2)))
    e0 = _unit(np.random.default_rng(0).normal(size=16))
    e1 = _unit(np.random.default_rng(1).normal(size=16))
    nan = np.full(16, np.nan, np.float32)
    rows = [
        # id, m north, heading, pano, capture_date, phash, CLIP embedding
        (1, 0, 10, "P1", "2019-05-01", base, e0),                   # pano rule with 2
        (2, 100, 350, "P1", "2023-06-01", other, _emb_like(e0, 0.992, 2)),
        (3, 0, 190, "P1", "2023-06-01", base, e0),                  # opposite heading -> no pair
        (11, 300, 0, "P2", None, other, e1),                        # same pano, different picture
        (12, 310, 0, "P2", None, other, _emb_like(e1, 0.90, 3)),    # (backfilled pano_id) -> no pair
        (4, 500, 90, None, None, other, _emb_like(e1, 0.5, 4)),     # spot rule with 5 (0.5 m apart,
        (5, 500.5, 100, None, None, base, _emb_like(e1, 0.3, 5)),   # different pictures)
        (6, 1000, 0, None, "2020-01-01", base, e0),                 # img rule with 7 (20 m, cos 1)
        (7, 1020, 5, None, "2021-01-01", base ^ 0b11, e0),
        (8, 1040, 5, None, None, base, _emb_like(e0, 0.97, 6)),     # same phash, ordinary neighbour
        (9, 2000, 0, None, None, base, nan),                        # no embeddings: identical phash
        (13, 2010, 0, None, None, base, nan),                       #   fallback -> img rule
        (10, 2001, 0, None, None, base, e0),                        # not eligible (no_imagery)
    ]
    df = pd.DataFrame([r[:6] for r in rows],
                      columns=["id", "north", "heading", "pano_id", "capture_date", "phash"])
    df["latitude"] = 47.5 + df["north"] * M
    df["longitude"] = 19.05
    emb = np.stack([r[6] for r in rows]).astype(np.float32)
    return df, emb


def test_dup_rules():
    df, emb = _frames()
    pairs = fq.find_dup_pairs(df, eligible=(df["id"] != 10).to_numpy(), emb=emb)
    got = {(int(a), int(b)): r for a, b, r in zip(pairs.id_a, pairs.id_b, pairs.rule)}
    assert got == {(1, 2): "pano", (4, 5): "spot", (6, 7): "img", (9, 13): "img"}
    row = pairs.set_index(["id_a", "id_b"]).loc[(6, 7)]
    assert abs(row.dist_m - 20) < 0.1 and row.hamming == 2 and row.heading_diff == 5
    assert row.cos > 0.999


def test_dup_rules_without_embeddings_need_identical_phash():
    df, _ = _frames()
    pairs = fq.find_dup_pairs(df, eligible=(df["id"] != 10).to_numpy())
    got = {(int(a), int(b)): r for a, b, r in zip(pairs.id_a, pairs.id_b, pairs.rule)}
    # Fallback: an identical phash counts as an identical picture (11~12 share it);
    # 6~7 / 7~8 differ by 2 bits -> not identical; the pano rule needs a cosine.
    assert got == {(4, 5): "spot", (9, 13): "img", (11, 12): "img"}


def test_dup_representative_choice():
    df, emb = _frames()
    pairs = fq.find_dup_pairs(df, eligible=(df["id"] != 10).to_numpy(), emb=emb)
    dup_of, cluster = fq.cluster_dups(df, pairs)
    d = dict(zip(df["id"], dup_of))
    assert d[1] == 2 and pd.isna(d[2])            # latest capture_date wins
    assert d[4] == 5 and pd.isna(d[5])            # no dates -> highest id (latest download) wins
    assert d[6] == 7 and pd.isna(d[7])
    assert d[9] == 13 and pd.isna(d[13])
    assert all(pd.isna(d[i]) for i in (3, 8, 10, 11, 12))
    assert cluster.notna().sum() == 8

    # An otherwise-flagged frame is never preferred as the representative.
    flagged = df["id"].isin([2, 5]).to_numpy()
    dup_of, _ = fq.cluster_dups(df, pairs, flagged=flagged)
    d = dict(zip(df["id"], dup_of))
    assert d[2] == 1 and pd.isna(d[1])
    assert d[5] == 4 and pd.isna(d[4])


def test_union_find_transitive():
    df = pd.DataFrame({"id": [1, 2, 3, 4], "capture_date": [None] * 4})
    pairs = pd.DataFrame({"id_a": [1, 2], "id_b": [2, 3]})
    dup_of, cluster = fq.cluster_dups(df, pairs)
    assert dup_of[0] == 3 and dup_of[1] == 3       # 1~2~3 is one cluster, highest id kept
    assert pd.isna(dup_of[2]) and pd.isna(dup_of[3]) and pd.isna(cluster[3])


# --- decide ------------------------------------------------------------------
def _row(i, **kw):
    """A healthy sunny road frame; override single fields per test row."""
    r = dict(id=i, exists=True, readable=True, md5="x" * 32, no_imagery=False,
             latitude=47.0 + i * 0.01, longitude=19.0, heading=0.0, pano_id=None,
             capture_date=None, phash=f"{i * 0x9E3779B97F4A7C15 % 2 ** 64:016x}",
             road_prob=0.95, brightness=120.0, contrast=50.0, dark_frac=0.02,
             blur=300.0, blur_full=500.0, sharp_p90=900.0)
    r.update({f"p_{c}": 0.0 for c in fq.CATEGORIES})
    r["p_road"] = 0.9
    r.update(kw)
    return r


def test_decide_rows():
    rows = [
        _row(1, capture_date="2024-01-01"),
        # Shaded road under trees: dark-ish, lots of black pixels, some "night" - still valid.
        _row(2, brightness=62.0, dark_frac=0.38, p_road=0.7, p_night=0.2, road_prob=0.8),
        # Smooth fresh asphalt: no texture in the road region, frame as a whole is sharp.
        _row(3, blur=4.0, blur_full=450.0, sharp_p90=1100.0),
        # Unpaved / broken road with a middling road filter score stays in.
        _row(4, road_prob=0.62, p_road=0.8),
        _row(5, md5=fq.PLACEHOLDER_MD5, brightness=228.0, contrast=1.0, road_prob=0.1, p_road=0.0),
        _row(6, exists=False, readable=False, brightness=np.nan, road_prob=np.nan),
        _row(7, road_prob=0.2, p_road=0.1, p_indoor=0.8),
        _row(8, brightness=20.0, dark_frac=0.9, p_road=0.3, p_night=0.6),
        _row(9, blur=3.0, blur_full=10.0, sharp_p90=15.0),
        _row(10, p_road=0.1, p_hood=0.85),           # own vehicle clearly in view
        _row(11, p_road=0.05, p_field=0.5, p_water=0.3, road_prob=0.95),  # road filter wins -> keep
        _row(12, p_road=0.1, p_wall=0.6),            # wall-ish below the 0.7 cut -> keep
        _row(13, latitude=47.01, heading=10.0, capture_date="2018-01-01"),  # same spot as id 1
        _row(14, brightness=228.0, contrast=2.0),    # heuristic placeholder (md5 differs)
        _row(15, p_road=0.1, p_blocked=0.99, p_tunnel_garage=0.0),  # obstructed rule disabled
        _row(16, p_road=0.1, p_tunnel_garage=0.9),
        _row(17, p_road=0.1, p_blocked=0.7),         # vehicle ahead: labeller still rates these
        _row(18, p_hood=0.4, pano_id="CAoSLEFGMVFpcE" + "x" * 22),  # dashcam user photosphere
        _row(19, p_hood=0.4, pano_id="abcdefghijklmnopqrstuv"),     # same score, Google car -> keep
        _row(20, road_prob=0.7, pano_id="CAoSLEFGMVFpcE" + "y" * 22),  # user photosphere, weak road
        _row(21, road_prob=0.7),                                     # same score, Google car -> keep
        _row(22, p_road=0.0, p_wall=0.95),           # wall rule disabled (0/1 in the blind check)
    ]
    out, pairs = fq.decide(pd.DataFrame(rows))
    got = dict(zip(out["id"], out["reasons"]))
    assert all(got[i] == "" for i in (1, 2, 3, 4, 11, 12, 15, 17, 19, 21, 22))
    assert got[5] == "no_imagery" and got[14] == "no_imagery"
    assert got[6] == "missing_image"
    assert got[7] == "not_road|indoor"
    assert got[8] == "dark"
    assert got[9] == "blur"
    assert got[10] == "hood"
    assert got[18] == "hood" and got[20] == "not_road"
    assert got[13] == "duplicate"
    assert got[16] == "tunnel_garage"
    assert out.set_index("id").loc[13, "dup_of"] == 1
    assert out["usable"].tolist() == [r == "" for r in out["reasons"]]
    assert len(pairs) == 1
    # Reasons always come out in the canonical order.
    for r in out["reasons"]:
        parts = [x for x in r.split("|") if x]
        assert parts == sorted(parts, key=fq.REASONS.index)


def test_decide_thresholds_are_overridable():
    df = pd.DataFrame([_row(1, brightness=62.0, dark_frac=0.38)])
    out, _ = fq.decide(df, dict(fq.THRESHOLDS, dark_brightness_max=70.0))
    assert out["reasons"].tolist() == ["dark"]


def test_build_payload():
    out, _ = fq.decide(pd.DataFrame([_row(1, capture_date="2024-01-01"),
                                     _row(2, latitude=47.01, heading=5.0),
                                     _row(3, exists=False, brightness=np.nan, road_prob=np.nan, blur=np.nan)]))
    p = [fq.build_payload(r) for _, r in out.iterrows()]
    assert p[0] == {"usable": True, "reasons": [], "road_prob": 0.95, "blur": 300.0,
                    "brightness": 120.0, "dup_of": None, "version": 1}
    assert p[1]["usable"] is False and p[1]["reasons"] == ["duplicate"] and p[1]["dup_of"] == 1
    assert p[2] == {"usable": False, "reasons": ["missing_image"], "road_prob": None, "blur": None,
                    "brightness": None, "dup_of": None, "version": 1}
    assert list(p[0]) == ["usable", "reasons", "road_prob", "blur", "brightness", "dup_of", "version"]
