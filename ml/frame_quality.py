#!/usr/bin/env python3
"""
Frame-quality audit: flag Street View frames that should NOT count toward road
quality (not a road, indoor / tunnel / garage, wall, obstruction, own-car hood,
night / very dark, blur, "no imagery" placeholder, duplicate panos).

A broken, shaded, patched or unpaved road is a VALID frame. Smooth fresh
asphalt has almost no texture in the road region, so the blur rule never looks
at the road-region Laplacian alone (it needs the WHOLE frame to be soft).
The wall / obstructed rules are computed but disabled (see THRESHOLDS).
Duplicates = near-identical pictures by CLIP cosine, or the same spot (see
find_dup_pairs). Output key: analysis_metadata.frame_quality (see build_payload);
consumers skip a frame only when frame_quality.usable is false.

Everything is cached under ml/cache/frame_quality/ and every stage is
resumable / idempotent:

  frames.csv          manifest from Postgres (read-only SELECT)
  clip_NNNNN.npz      L2-normalised CLIP-B/32 image embeddings (float16), by id range
  text_emb.npz        cached CLIP text embeddings for all prompts ever used
  clip_scores.csv     road_prob + p_<category> (recomputed cheaply from embeddings)
  pixels.csv          cv2 pixel statistics + dhash / phash (hex) + md5
  dup_pairs.csv       matched duplicate pairs (for eyeballing)
  frame_quality.csv   final per-frame decision
  candidates/         review candidates per reason / borderline feature (CSV)
  sheets/             contact sheets for visual review

Usage (PY = /Users/i/Dev/smooth-route/.venv/bin/python):
  PY ml/frame_quality.py manifest
  PY ml/frame_quality.py clip
  PY ml/frame_quality.py pixels
  PY ml/frame_quality.py dups
  PY ml/frame_quality.py decide
  PY ml/frame_quality.py all                      # the five stages above
  PY ml/frame_quality.py calibrate
  PY ml/frame_quality.py sheet --reason not_road --n 12 --seed 0
  PY ml/frame_quality.py sheet --borderline road_prob --n 12
  PY ml/frame_quality.py sheet --ids 1,2,3 [--blind --cols 2 --rows 2 --quality 70 --out DIR]
  PY ml/frame_quality.py candidates               # CSVs + id lists per reason / borderline
  PY ml/frame_quality.py write                    # dry run
  PY ml/frame_quality.py write --commit --backup data/backups/<fresh pg_dump -Fc>.dump
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time

import cv2
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ML_DIR = os.path.join(ROOT, "ml")
IMAGE_DIR = os.path.join(ROOT, "data", "images")
CACHE = os.path.join(ML_DIR, "cache", "frame_quality")
LABELS = os.path.join(ML_DIR, "labels.csv")
DATASET_V2 = os.path.join(ML_DIR, "cache", "dataset_v2.csv")

FRAMES_CSV = os.path.join(CACHE, "frames.csv")
PIXELS_CSV = os.path.join(CACHE, "pixels.csv")
CLIP_SCORES_CSV = os.path.join(CACHE, "clip_scores.csv")
TEXT_EMB = os.path.join(CACHE, "text_emb.npz")
DUP_PAIRS_CSV = os.path.join(CACHE, "dup_pairs.csv")
QUALITY_CSV = os.path.join(CACHE, "frame_quality.csv")
SHEET_DIR = os.path.join(CACHE, "sheets")

CLIP_MODEL = "openai/clip-vit-base-patch32"
CLIP_BATCH = 64
CLIP_SHARD = 1024          # ids per shard: shard k holds ids k*1024+1 .. (k+1)*1024
PIXEL_WORKERS = 8
PAYLOAD_VERSION = 1

# md5 of the Street View "Sorry, we have no imagery here" placeholder (6227 bytes).
PLACEHOLDER_MD5 = "ce4809c142f3b1693b2748062274b244"

# All tunable numbers live here. They are initial guesses, meant to be
# calibrated with the `calibrate` and `sheet` subcommands.
THRESHOLDS = {
    # --- image geometry -----------------------------------------------------
    "logo_strip_px": 22,          # bottom rows ignored everywhere (Google logo + copyright strip)
    "road_region_top": 0.45,      # road region = rows 45%..100% of the trimmed image ...
    "road_region_side": 0.10,     # ... and the central 80% of the width
    # --- no-imagery placeholder ----------------------------------------------
    "no_imagery_contrast_max": 6.0,     # gray std below this AND ...
    "no_imagery_brightness_min": 180.0,  # ... mean gray above this => uniform light-gray placeholder
    # --- not a road ------------------------------------------------------------
    # Calibrated 2026-11-26 on the 1903 labelled RQI 1-4 frames (all valid road
    # views: the labeller rated them) + a blind visual spot check. Rule of thumb:
    # a threshold may not flag labelled frames at a higher rate than unlabelled
    # ones, otherwise it is cutting valid (often bad or shaded) roads.
    "road_prob_min": 0.5,         # not_road if the extract_features_v2 CLIP road_prob is below this
                                  # (0.5: 107 frames, 0 labelled; 0.6 already hits 2 labelled)
    "caos_road_prob_min": 0.9,    # stricter cut for user photospheres (pano_id 'CAoS...'): in the
                                  # blind check 9 of 13 were junk (footpaths, bridges, plazas, hoods)
    # --- scene categories (zero-shot CLIP, softmax over all category prompts) --
    "category_road_max": 0.3,     # indoor/tunnel/wall/obstructed only fire when p_road is below this
    "indoor_prob_min": 0.5,       # indoor:        p_indoor >= this (9 frames, 0 labelled)
    "tunnel_garage_prob_min": 0.5,  # tunnel_garage: p_tunnel_garage >= this
    # wall + obstructed are DISABLED (threshold > 1): the zero-shot prompts do not
    # separate them. At 0.5 they flagged labelled frames at a higher rate than the
    # rest (wall 2/8, obstructed 52/164: the labeller rates roads with a truck
    # ahead), and the blind check judged 0/1 wall and 0/2 obstructed flags junk.
    # Real walls showed up under tunnel_garage / blur instead. Scores stay in the CSV.
    "wall_prob_min": 1.01,        # wall:          p_wall >= this
    "blocked_prob_min": 1.01,     # obstructed:    p_blocked >= this
    "hood_prob_caos_min": 0.3,    # hood: user photosphere (pano_id 'CAoS...', dashcam rigs) and
                                  # p_hood >= this (57 frames, 0 labelled) ...
    "hood_prob_min": 0.8,         # ... or any frame with p_hood >= this (Google-car frames never
                                  # show the own vehicle; at 0.5 it hit 12 labelled frames)
    # --- dark / night (the data set has almost no dark frames: min brightness ~55) --
    "dark_brightness_max": 45.0,  # dark if mean gray (0-255) is below this
    "dark_frac_max": 0.6,         # dark if more than this fraction of pixels is < 30
    "night_prob_min": 0.3,        # dark also if p_night >= this ...
    "night_brightness_max": 80.0,  # ... and mean gray is below this (street-lit night shots)
    # --- blur (BOTH must hold; never the road-region `blur` alone: smooth fresh
    # asphalt has almost no texture there) ------------------------------------------
    "blur_sharp_p90_max": 650.0,  # blur if the 90th-pct tile Laplacian variance is below this ...
    "blur_full_max": 340.0,       # ... AND the whole-frame Laplacian variance is below this
                                  # (labelled minima: sharp_p90 660, blur_full 312; 5 frames, 0 labelled)
    # --- duplicates (see find_dup_pairs for the measurements behind these) ------
    "dup_heading_max_deg": 30.0,  # all dup rules: circular heading difference <= this
    "dup_img_m": 25.0,            # rule img: haversine distance <= this ...
    "dup_img_cos": 0.995,         # ... and CLIP image cosine >= this (near-identical picture)
    "dup_phash_exact_max": 0,     # ... (fallback when a frame has no embedding: phash Hamming <= this)
    "dup_spot_m": 1.0,            # rule spot: same spot sampled twice (haversine <= this)
    "dup_pano_cos": 0.99,         # rule pano: same pano_id AND CLIP cosine >= this
}

# Zero-shot categories. Edit freely: the scores are recomputed from the cached
# image embeddings at decide time (only new prompt texts need the CLIP text
# tower once; they are cached in text_emb.npz). Softmax runs over ALL prompts
# of all categories and is summed per category -> column p_<category>.
# Wording notes (measured on the labelled valid frames): CLIP ignores negation,
# so "... with no road" prompts attracted ordinary road frames (median p_road
# was 0.32); "street view photo of ..." on tunnel / blocked / water did the
# same. The plain wording below lifts the median p_road of valid frames to 0.64.
CATEGORY_PROMPTS = {
    "road": [
        "a street view photo of a paved asphalt road",
        "a street view photo of an unpaved dirt or gravel road",
        "a street view photo of a damaged road with potholes and cracks",
        "a street view photo of a road in the shade of trees",
    ],
    "indoor": [
        "a street view photo of the inside of a building",
        "a street view photo of the inside of a shop, a lobby or a restaurant",
    ],
    "tunnel_garage": [
        "a photo of the inside of a road tunnel",
        "a photo of the inside of an underground parking garage",
    ],
    "wall": [
        "a street view photo of a close-up of a wall or a building facade filling the view",
        "a street view photo of a close-up of a fence or a hedge filling the view",
    ],
    "blocked": [
        "a photo of the back of a large truck filling the whole picture",
        "a photo of the side of a bus or a van filling the whole picture",
    ],
    "hood": [
        "a street view photo of the hood or bonnet of the car the camera is mounted on covering the bottom of the picture",
        "a street view photo of the dashboard of the car the camera is mounted on covering the bottom of the picture",
    ],
    "night": [
        "a street view photo of a street at night",
        "a very dark photo",
    ],
    "blurry": [
        "a very blurry, out of focus photo",
        "a street view photo with heavy motion blur",
    ],
    "field": [
        "a street view photo of a field or a lawn",
        "a street view photo of a forest or a park",
    ],
    "water": [
        "a photo of a river, a lake or the sea",
        "a photo of open water",
    ],
}
CATEGORIES = list(CATEGORY_PROMPTS)
P_COLS = [f"p_{c}" for c in CATEGORIES]

REASONS = ["missing_image", "no_imagery", "not_road", "indoor", "tunnel_garage",
           "wall", "obstructed", "hood", "dark", "blur", "duplicate"]

PIXEL_COLS = ["id", "readable", "bytes", "md5", "brightness", "contrast",
              "dark_frac", "bright_frac", "sat_mean", "blur", "blur_full",
              "sharp_p90", "edge_frac", "no_imagery", "dhash", "phash"]

# feature -> (direction that gets FLAGGED, THRESHOLDS key). Used by
# `calibrate` and by `sheet --borderline`.
FEATURE_RULES = {
    "road_prob": ("lt", "road_prob_min"),
    "p_indoor": ("ge", "indoor_prob_min"),
    "p_tunnel_garage": ("ge", "tunnel_garage_prob_min"),
    "p_wall": ("ge", "wall_prob_min"),
    "p_blocked": ("ge", "blocked_prob_min"),
    "p_hood": ("ge", "hood_prob_min"),         # (CAoS frames use hood_prob_caos_min)
    "p_night": ("ge", "night_prob_min"),
    "brightness": ("lt", "dark_brightness_max"),
    "dark_frac": ("gt", "dark_frac_max"),
    "sharp_p90": ("lt", "blur_sharp_p90_max"),
    "blur_full": ("lt", "blur_full_max"),
}


def ensure_cache():
    """Create the cache dir. ml/cache/frame_quality/ is not covered by the
    repo .gitignore, so it carries its own catch-all .gitignore."""
    os.makedirs(CACHE, exist_ok=True)
    gi = os.path.join(CACHE, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w") as f:
            f.write("*\n")


# ---------------------------------------------------------------------------
# Pure helpers (no torch, no DB)
# ---------------------------------------------------------------------------
def heading_diff(a, b):
    """Circular difference between two headings in degrees, in [0, 180]."""
    d = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)) % 360.0
    return np.where(d > 180.0, 360.0 - d, d)


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (vectorised)."""
    r = 6371008.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _bits_to_int(bits):
    v = 0
    for b in np.asarray(bits).ravel():
        v = (v << 1) | int(bool(b))
    return v


def dhash(gray):
    """64-bit difference hash: 9x8 resize, left > right."""
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    return _bits_to_int(small[:, :-1] > small[:, 1:])


def phash(gray):
    """64-bit perceptual hash: 32x32 gray -> DCT -> top-left 8x8, DC excluded
    from the median (its bit is always 0) -> median threshold."""
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(small)[:8, :8].ravel()
    med = np.median(low[1:])
    bits = low > med
    bits[0] = False
    return _bits_to_int(bits)


def hamming(a, b):
    """Hamming distance between 64-bit hashes (ints or uint64 arrays)."""
    x = np.bitwise_xor(np.asarray(a, dtype=np.uint64), np.asarray(b, dtype=np.uint64))
    out = np.bitwise_count(x).astype(int)
    return int(out) if out.ndim == 0 else out


def image_features(img_bgr, T=THRESHOLDS):
    """Pixel statistics of one decoded BGR image (the logo strip is cut off)."""
    strip = int(T["logo_strip_px"])
    img = img_bgr[: max(1, img_bgr.shape[0] - strip)]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    r0 = int(h * T["road_region_top"])
    c0, c1 = int(w * T["road_region_side"]), int(w * (1 - T["road_region_side"]))
    tiles = [lap[int(h * i / 4): int(h * (i + 1) / 4),
                 int(w * j / 6): int(w * (j + 1) / 6)].var()
             for i in range(4) for j in range(6)]
    brightness = float(gray.mean())
    contrast = float(gray.std())
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1]
    return {
        "brightness": brightness,
        "contrast": contrast,
        "dark_frac": float((gray < 30).mean()),
        "bright_frac": float((gray > 245).mean()),
        "sat_mean": float(sat.mean()),
        "blur": float(lap[r0:, c0:c1].var()),
        "blur_full": float(lap.var()),
        "sharp_p90": float(np.percentile(tiles, 90)),
        "edge_frac": float((cv2.Canny(gray, 50, 150) > 0).mean()),
        "no_imagery": bool(contrast < T["no_imagery_contrast_max"]
                           and brightness > T["no_imagery_brightness_min"]),
        "dhash": f"{dhash(gray):016x}",
        "phash": f"{phash(gray):016x}",
    }


def pixel_features(job):
    """Worker: (id, path) -> feature row dict. Never raises."""
    fid, path = job
    row = {c: "" for c in PIXEL_COLS}
    row.update(id=fid, readable=False)
    try:
        with open(path, "rb") as f:
            data = f.read()
        row["bytes"] = len(data)
        row["md5"] = hashlib.md5(data).hexdigest()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            row.update(image_features(img))
            row["readable"] = True
            row["no_imagery"] = bool(row["no_imagery"] or row["md5"] == PLACEHOLDER_MD5)
    except OSError:
        pass
    return row


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _hash_array(series):
    """Column of hex strings / ints / NaN -> uint64 array (0 where missing)."""
    out = np.zeros(len(series), dtype=np.uint64)
    for i, v in enumerate(series):
        if isinstance(v, str) and v:
            out[i] = int(v, 16)
        elif isinstance(v, (int, np.integer)):
            out[i] = int(v)
    return out


DUP_RULES = ["img", "spot", "pano"]   # priority order when a pair matches several


def find_dup_pairs(df, T=THRESHOLDS, eligible=None, emb=None):
    """Matched duplicate pairs among eligible frames.

    A duplicate is the same panorama seen twice in (nearly) the same direction:
    the segment median would count that stretch of road twice. All rules need a
    circular heading difference <= dup_heading_max_deg:
      img   haversine <= dup_img_m and a near-identical picture: CLIP image
            cosine >= dup_img_cos (phash Hamming <= dup_phash_exact_max when a
            frame has no embedding)
      spot  haversine <= dup_spot_m: the same spot sampled twice, even if the
            stored pictures differ (re-downloaded after a newer capture)
      pano  same non-null pano_id and CLIP cosine >= dup_pano_cos

    Why not phash or pano_id alone (measured 2026-11-26 on 36k candidate pairs
    within 25 m and 30 deg): consecutive route samples ~9 m apart score CLIP
    cosine 0.90-0.98 and phash Hamming 2-8, so a phash cut flags ordinary
    neighbours (it marked 23% of the labelled frames). Near-identical pictures
    form a separate mode at cosine >= 0.995 (~250 pairs). pano_id is backfilled
    from the Metadata API after the download and often does not describe the
    stored picture (816 same-pano same-heading pairs, only 155 near-identical).

    df needs: id, latitude, longitude, heading, pano_id, phash.
    emb: optional float array [len(df), d] of L2-normalised CLIP embeddings
    aligned with df rows (NaN rows = no embedding).
    Returns DataFrame id_a < id_b, dist_m, heading_diff, cos, hamming, same_pano, rule.
    """
    from scipy.spatial import cKDTree

    cols = ["id_a", "id_b", "dist_m", "heading_diff", "cos", "hamming", "same_pano", "rule"]
    keep = np.ones(len(df), dtype=bool) if eligible is None else np.asarray(eligible, dtype=bool)
    keep = keep & (df["latitude"].notna() & df["longitude"].notna()
                   & df["heading"].notna()).to_numpy()
    d = df[keep].reset_index(drop=True)
    E = None if emb is None else np.asarray(emb, dtype=np.float32)[keep]
    if len(d) < 2:
        return pd.DataFrame(columns=cols)

    lat = d["latitude"].to_numpy(float)
    lon = d["longitude"].to_numpy(float)
    head = d["heading"].to_numpy(float)
    ids = d["id"].to_numpy()
    ph = _hash_array(d["phash"]) if "phash" in d else np.zeros(len(d), np.uint64)
    has_ph = d["phash"].notna().to_numpy() if "phash" in d else np.zeros(len(d), bool)
    pano = d["pano_id"].astype(object).where(d["pano_id"].notna(), None).to_numpy() \
        if "pano_id" in d else np.full(len(d), None, dtype=object)

    # Local equirectangular projection to metres; KD-tree for the radius join.
    r = 6371008.8
    x = np.radians(lon - lon.mean()) * r * np.cos(np.radians(lat.mean()))
    y = np.radians(lat - lat.mean()) * r
    radius = max(T["dup_img_m"], T["dup_spot_m"])
    near = cKDTree(np.c_[x, y]).query_pairs(radius * 1.02 + 0.5, output_type="ndarray")

    # Same-pano pairs via a self-join (they may be farther apart than the radius).
    pos = pd.DataFrame({"pano": pano, "i": np.arange(len(d))}).dropna()
    pos = pos[pos.duplicated("pano", keep=False)]
    j = pos.merge(pos, on="pano")
    j = j[j["i_x"] < j["i_y"]]
    cand = np.unique(np.vstack([near.reshape(-1, 2),
                                j[["i_x", "i_y"]].to_numpy().reshape(-1, 2)]).astype(int), axis=0)
    if len(cand) == 0:
        return pd.DataFrame(columns=cols)
    a, b = cand[:, 0], cand[:, 1]

    dist = haversine_m(lat[a], lon[a], lat[b], lon[b])
    hd = heading_diff(head[a], head[b])
    ham = hamming(ph[a], ph[b])
    same = np.array([pa is not None and pa == pb for pa, pb in zip(pano[a], pano[b])], dtype=bool)
    cos = (E[a] * E[b]).sum(1) if E is not None else np.full(len(cand), np.nan)
    no_cos = ~np.isfinite(cos)
    identical = np.where(no_cos, has_ph[a] & has_ph[b] & (ham <= T["dup_phash_exact_max"]),
                         np.nan_to_num(cos, nan=-1.0) >= T["dup_img_cos"])

    ok_h = hd <= T["dup_heading_max_deg"]
    matched = {
        "img": ok_h & (dist <= T["dup_img_m"]) & identical,
        "spot": ok_h & (dist <= T["dup_spot_m"]),
        "pano": ok_h & same & (np.nan_to_num(cos, nan=-1.0) >= T["dup_pano_cos"]),
    }
    rule = np.full(len(cand), "", dtype=object)
    for name in reversed(DUP_RULES):          # highest priority written last
        rule[matched[name]] = name

    ia, ib = ids[a], ids[b]
    out = pd.DataFrame({
        "id_a": np.minimum(ia, ib), "id_b": np.maximum(ia, ib), "dist_m": dist,
        "heading_diff": hd, "cos": cos, "hamming": ham, "same_pano": same, "rule": rule})
    out = out[out["rule"] != ""].sort_values(["id_a", "id_b"]).reset_index(drop=True)
    return out[cols]


def cluster_dups(df, pairs, flagged=None):
    """Union-find over pairs -> (dup_of, cluster_id) Series indexed like df.

    Representative per cluster: not otherwise flagged first, then the latest
    capture_date (missing date = oldest), then the highest id (the most recent
    download, i.e. the panorama Google served last for that spot). The representative
    and all unclustered frames get dup_of = <NA>.
    """
    dup_of = pd.Series(pd.NA, index=df.index, dtype="Int64")
    cluster = pd.Series(pd.NA, index=df.index, dtype="Int64")
    if len(pairs) == 0:
        return dup_of, cluster
    members = pd.unique(np.concatenate([pairs["id_a"].to_numpy(), pairs["id_b"].to_numpy()]))
    uf = UnionFind(int(m) for m in members)
    for ia, ib in zip(pairs["id_a"], pairs["id_b"]):
        uf.union(int(ia), int(ib))

    sub = df[df["id"].isin(members)].copy()
    sub["_root"] = [uf.find(int(i)) for i in sub["id"]]
    sub["_flag"] = False if flagged is None else np.asarray(flagged, dtype=bool)[df["id"].isin(members)]
    dates = pd.to_datetime(sub["capture_date"], errors="coerce") if "capture_date" in sub \
        else pd.Series(pd.NaT, index=sub.index)
    sub["_date"] = dates.fillna(pd.Timestamp("1900-01-01"))
    sub = sub.sort_values(["_root", "_flag", "_date", "id"],
                          ascending=[True, True, False, False])
    rep = sub.groupby("_root")["id"].transform("first")
    is_dup = sub["id"] != rep
    dup_of.loc[sub.index[is_dup]] = rep[is_dup].astype("Int64")
    cluster.loc[sub.index] = sub["_root"].astype("Int64")
    return dup_of, cluster


def _num(df, col, default):
    if col in df:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(default, index=df.index, dtype=float)


def _flag(df, col):
    if col not in df:
        return pd.Series(False, index=df.index)
    s = df[col]
    if s.dtype == bool:
        return s
    return s.astype(str).str.lower().isin(["true", "1", "1.0"])


def base_masks(df, T=THRESHOLDS):
    """Boolean mask per non-duplicate reason (ordered like REASONS).

    NaN features never fire a rule (comparisons with NaN are False).
    """
    exists = _flag(df, "exists") if "exists" in df else pd.Series(True, index=df.index)
    readable = _flag(df, "readable") if "readable" in df else pd.Series(True, index=df.index)
    missing = ~(exists & readable)

    brightness = _num(df, "brightness", np.nan)
    contrast = _num(df, "contrast", np.nan)
    md5 = df["md5"].astype(str) if "md5" in df else pd.Series("", index=df.index)
    no_img = ~missing & (
        ((contrast < T["no_imagery_contrast_max"]) & (brightness > T["no_imagery_brightness_min"]))
        | (md5 == PLACEHOLDER_MD5) | _flag(df, "no_imagery"))

    live = ~missing & ~no_img          # content rules only apply to real pictures
    road_prob = _num(df, "road_prob", np.nan)
    p = {c: _num(df, f"p_{c}", 0.0) for c in CATEGORIES}
    low_road = p["road"] < T["category_road_max"]
    caos = (df["pano_id"].fillna("").astype(str).str.startswith("CAoS") if "pano_id" in df
            else pd.Series(False, index=df.index))

    m = {
        "missing_image": missing,
        "no_imagery": no_img,
        # Not a road: the v2 CLIP road filter (same prompts as training) says so;
        # user photospheres need a clearly road-like picture.
        "not_road": live & ((road_prob < T["road_prob_min"])
                            | (caos & (road_prob < T["caos_road_prob_min"]))),
        # Scene categories: confident category AND low road probability.
        "indoor": live & (p["indoor"] >= T["indoor_prob_min"]) & low_road,
        "tunnel_garage": live & (p["tunnel_garage"] >= T["tunnel_garage_prob_min"]) & low_road,
        "wall": live & (p["wall"] >= T["wall_prob_min"]) & low_road,
        "obstructed": live & (p["blocked"] >= T["blocked_prob_min"]) & low_road,
        # Own vehicle in the bottom of the frame: dashcam-style user photospheres.
        "hood": live & (((p["hood"] >= T["hood_prob_caos_min"]) & caos)
                        | (p["hood"] >= T["hood_prob_min"])),
        # Dark: globally dark, mostly black, or a (street-lit) night shot.
        "dark": live & ((brightness < T["dark_brightness_max"])
                        | (_num(df, "dark_frac", np.nan) > T["dark_frac_max"])
                        | ((p["night"] >= T["night_prob_min"])
                           & (brightness < T["night_brightness_max"]))),
        # Blur: nothing in the frame is sharp AND the whole frame is soft.
        "blur": live & (_num(df, "sharp_p90", np.nan) < T["blur_sharp_p90_max"])
                     & (_num(df, "blur_full", np.nan) < T["blur_full_max"]),
    }
    return {k: v.fillna(False).astype(bool) for k, v in m.items()}


def decide(df, T=THRESHOLDS, emb=None):
    """Features -> copy of df with `usable`, `reasons` ('|'-joined), `dup_of`
    (Int64), `dup_cluster`. Also returns the matched dup pairs.
    emb: optional CLIP embeddings aligned with df rows (see aligned_embeddings)."""
    out = df.copy()
    masks = base_masks(out, T)
    flagged = np.zeros(len(out), dtype=bool)
    for m in masks.values():
        flagged |= m.to_numpy()

    eligible = ~(masks["missing_image"] | masks["no_imagery"]).to_numpy()
    pairs = find_dup_pairs(out, T, eligible=eligible, emb=emb)
    dup_of, cluster = cluster_dups(out, pairs, flagged=flagged)
    masks["duplicate"] = dup_of.notna()

    reasons = pd.Series("", index=out.index, dtype=object)
    for name in REASONS:
        mk = masks[name].to_numpy()
        reasons[mk] = [r + "|" + name if r else name for r in reasons[mk]]
    out["usable"] = reasons == ""
    out["reasons"] = reasons
    out["dup_of"] = dup_of
    out["dup_cluster"] = cluster
    return out, pairs


def build_payload(row):
    """Per-frame JSON payload written under analysis_metadata.frame_quality."""
    def f(v, nd):
        return None if v is None or pd.isna(v) else round(float(v), nd)

    reasons = row["reasons"]
    reasons = [r for r in str(reasons).split("|") if r] if isinstance(reasons, str) else []
    dup = row.get("dup_of")
    return {
        "usable": bool(row["usable"]),
        "reasons": reasons,
        "road_prob": f(row.get("road_prob"), 3),
        "blur": f(row.get("blur"), 1),
        "brightness": f(row.get("brightness"), 1),
        "dup_of": None if dup is None or pd.isna(dup) else int(dup),
        "version": PAYLOAD_VERSION,
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        for line in open(env):
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("DATABASE_URL not set (env var or .env in the repo root)")


def load_frames():
    if not os.path.exists(FRAMES_CSV):
        sys.exit(f"{FRAMES_CSV} missing - run `manifest` first")
    return pd.read_csv(FRAMES_CSV, dtype={"pano_id": str, "image_url": str, "capture_date": str,
                                          "filename": str, "path": str})


def load_pixels():
    if not os.path.exists(PIXELS_CSV):
        return pd.DataFrame(columns=PIXEL_COLS)
    df = pd.read_csv(PIXELS_CSV, dtype={"md5": str, "dhash": str, "phash": str})
    return df.drop_duplicates("id", keep="last")


def load_labels():
    """labels.csv -> DataFrame(filename, manual_rqi), one row per file."""
    lab = pd.read_csv(LABELS)
    lab = lab[lab["manual_rqi"].notna()].drop_duplicates("image_filename")
    return lab.rename(columns={"image_filename": "filename"})[["filename", "manual_rqi"]]


def shard_path(k):
    return os.path.join(CACHE, f"clip_{k:05d}.npz")


def load_embeddings():
    """All cached shards -> (ids int64, emb float32 [n, 512]); NaN rows dropped."""
    import glob
    ids, embs = [], []
    for p in sorted(glob.glob(os.path.join(CACHE, "clip_[0-9]*.npz"))):
        z = np.load(p)
        ids.append(z["ids"])
        embs.append(z["emb"].astype(np.float32))
    if not ids:
        return np.zeros(0, np.int64), np.zeros((0, 512), np.float32)
    ids, emb = np.concatenate(ids), np.concatenate(embs)
    ok = np.isfinite(emb).all(1)
    return ids[ok], emb[ok]


def aligned_embeddings(df):
    """CLIP embeddings aligned with df rows (NaN rows where a frame has none)."""
    ids, emb = load_embeddings()
    out = np.full((len(df), emb.shape[1] if emb.ndim == 2 else 512), np.nan, dtype=np.float32)
    pos = pd.Series(np.arange(len(ids)), index=ids)
    hit = df["id"].isin(pos.index).to_numpy()
    out[hit] = emb[pos.loc[df["id"][hit]].to_numpy()]
    return out


# ---------------------------------------------------------------------------
# CLIP (torch / transformers imported lazily)
# ---------------------------------------------------------------------------
_CLIP = {}


def _load_clip():
    if not _CLIP:
        # Never hit the network: the weights are already in the local HF cache.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        import torch
        from transformers import CLIPModel, CLIPProcessor
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        print(f">> loading {CLIP_MODEL} on {device} ...")
        _CLIP["proc"] = CLIPProcessor.from_pretrained(CLIP_MODEL, local_files_only=True)
        _CLIP["model"] = CLIPModel.from_pretrained(CLIP_MODEL, local_files_only=True).to(device).eval()
        _CLIP["device"] = device
    return _CLIP


def road_filter_prompts():
    """ROAD_PROMPTS / NOTROAD_PROMPTS of the existing v2 road filter (lazy:
    importing extract_features_v2 pulls in torch)."""
    if ML_DIR not in sys.path:
        sys.path.insert(0, ML_DIR)
    from extract_features_v2 import NOTROAD_PROMPTS, ROAD_PROMPTS
    return list(ROAD_PROMPTS), list(NOTROAD_PROMPTS)


def text_embeddings(prompts):
    """L2-normalised CLIP text embeddings (float32) + logit scale, cached by
    prompt text in text_emb.npz. Only loads the model for unseen prompts."""
    cache, scale = {}, None
    if os.path.exists(TEXT_EMB):
        z = np.load(TEXT_EMB, allow_pickle=False)
        cache = dict(zip(z["prompts"].tolist(), z["emb"]))
        scale = float(z["logit_scale"])
    todo = [p for p in prompts if p not in cache]
    if todo or scale is None:
        import torch
        c = _load_clip()
        with torch.no_grad():
            if todo:
                tinp = c["proc"](text=todo, return_tensors="pt", padding=True).to(c["device"])
                t = c["model"].get_text_features(**tinp)
                t = (t / t.norm(dim=-1, keepdim=True)).float().cpu().numpy()
                cache.update(zip(todo, t))
            scale = float(c["model"].logit_scale.exp().item())
        ensure_cache()
        np.savez(TEXT_EMB, prompts=np.array(list(cache)),
                 emb=np.stack(list(cache.values())).astype(np.float32),
                 logit_scale=np.float32(scale))
    return np.stack([cache[p] for p in prompts]).astype(np.float32), scale


def _softmax(x):
    x = x - x.max(axis=1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=1, keepdims=True)


def clip_scores(ids, emb):
    """Cached embeddings -> DataFrame(id, road_prob, p_<category>...)."""
    road, notroad = road_filter_prompts()
    t, scale = text_embeddings(road + notroad)
    out = {"id": ids}
    # Identical to extract_features_v2.extract_clip: softmax over the 4 prompts
    # of logit_scale * cosine, summed over the 2 road prompts.
    out["road_prob"] = _softmax(scale * emb @ t.T)[:, : len(road)].sum(1)
    flat = [(c, p) for c in CATEGORIES for p in CATEGORY_PROMPTS[c]]
    t2, _ = text_embeddings([p for _, p in flat])
    probs = _softmax(scale * emb @ t2.T)
    cats = np.array([c for c, _ in flat])
    for c in CATEGORIES:
        out[f"p_{c}"] = probs[:, cats == c].sum(1)
    return pd.DataFrame(out)


def _open_rgb(path):
    from PIL import Image
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return None


def _embed_images(paths):
    """Paths -> float16 [n, 512] L2-normalised (NaN rows for unreadable files)."""
    import torch
    from concurrent.futures import ThreadPoolExecutor
    c = _load_clip()
    out = np.full((len(paths), 512), np.nan, dtype=np.float32)
    with ThreadPoolExecutor(8) as pool:
        for i in range(0, len(paths), CLIP_BATCH):
            imgs = list(pool.map(_open_rgb, paths[i: i + CLIP_BATCH]))
            good = [k for k, im in enumerate(imgs) if im is not None]
            if not good:
                continue
            pix = c["proc"](images=[imgs[k] for k in good], return_tensors="pt")
            with torch.no_grad():
                try:
                    f = c["model"].get_image_features(**pix.to(c["device"]))
                except RuntimeError as e:
                    if c["device"] == "cpu":
                        raise
                    print(f"\n   MPS error ({e}); falling back to CPU")
                    c["model"] = c["model"].to("cpu")
                    c["device"] = "cpu"
                    f = c["model"].get_image_features(**pix.to("cpu"))
                f = (f / f.norm(dim=-1, keepdim=True)).float().cpu().numpy()
            out[i + np.array(good)] = f
    return out.astype(np.float16)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------
def cmd_manifest(args=None):
    import psycopg2
    ensure_cache()
    conn = psycopg2.connect(database_url())
    conn.set_session(readonly=True)
    try:
        df = pd.read_sql_query(
            "SELECT id, latitude, longitude, heading, pano_id, image_url, capture_date, "
            "dino_rqi_score, (analysis_metadata->>'dino_score') AS dino_score "
            "FROM street_view_images ORDER BY id", conn)
    finally:
        conn.close()
    df["filename"] = [os.path.basename(u) if isinstance(u, str) and u else "" for u in df["image_url"]]
    df["path"] = [os.path.join(IMAGE_DIR, f) if f else "" for f in df["filename"]]
    df["exists"] = [bool(p) and os.path.isfile(p) for p in df["path"]]
    df.to_csv(FRAMES_CSV, index=False)
    print(f"[manifest] {len(df)} rows -> {FRAMES_CSV}")
    print(f"           files present: {int(df['exists'].sum())}, missing: {int((~df['exists']).sum())}, "
          f"empty image_url: {int((df['filename'] == '').sum())}, "
          f"duplicate filenames: {int(df['filename'].duplicated().sum())}")
    print(f"           pano_id: {int(df['pano_id'].notna().sum())} "
          f"(CAoS user photospheres: {int(df['pano_id'].fillna('').str.startswith('CAoS').sum())}), "
          f"capture_date: {int(df['capture_date'].notna().sum())}, "
          f"dino_rqi_score null: {int(df['dino_rqi_score'].isna().sum())}")
    if (~df["exists"]).any():
        print("           missing ids:", df.loc[~df["exists"], "id"].tolist()[:30])


def cmd_clip(args=None):
    ensure_cache()
    fr = load_frames()
    fr = fr[fr["exists"]]
    shard_of = (fr["id"].to_numpy() - 1) // CLIP_SHARD
    todo = []
    for k in np.unique(shard_of):
        ids = fr["id"].to_numpy()[shard_of == k]
        p = shard_path(int(k))
        if os.path.exists(p) and set(ids) <= set(np.load(p)["ids"].tolist()):
            continue
        todo.append((int(k), ids, fr["path"].to_numpy()[shard_of == k].tolist()))
    print(f"[clip] {len(np.unique(shard_of))} shards, {len(todo)} to compute")
    t0 = time.time()
    for n, (k, ids, paths) in enumerate(todo, 1):
        emb = _embed_images(paths)
        tmp = shard_path(k) + ".tmp.npz"
        np.savez(tmp, ids=ids.astype(np.int64), emb=emb)
        os.replace(tmp, shard_path(k))
        print(f"   shard {k:05d} ({len(ids)} frames)  {n}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)

    ids, emb = load_embeddings()
    scores = clip_scores(ids, emb)
    scores.to_csv(CLIP_SCORES_CSV, index=False, float_format="%.6f")
    print(f"[clip] {len(scores)} embeddings -> {CLIP_SCORES_CSV}")
    road_prob_sanity(fr, scores)


def road_prob_sanity(fr, scores):
    """Compare our road_prob with dataset_v2.csv is_road_prob on labelled frames."""
    if not os.path.exists(DATASET_V2):
        print("[clip] sanity: dataset_v2.csv not found, skipped")
        return
    ref = pd.read_csv(DATASET_V2)[["image_filename", "is_road_prob"]]
    m = fr[["id", "filename"]].merge(scores[["id", "road_prob"]], on="id") \
        .merge(ref, left_on="filename", right_on="image_filename")
    if len(m) == 0:
        print("[clip] sanity: no overlap with dataset_v2.csv")
        return
    diff = (m["road_prob"] - m["is_road_prob"]).abs()
    print(f"[clip] road_prob sanity vs dataset_v2.csv on {len(m)}/{len(ref)} labelled frames: "
          f"pearson r={np.corrcoef(m['road_prob'], m['is_road_prob'])[0, 1]:.6f}, "
          f"max|diff|={diff.max():.5f}, mean|diff|={diff.mean():.5f}, "
          f"agree at 0.5: {((m['road_prob'] < 0.5) == (m['is_road_prob'] < 0.5)).mean():.4f}")


def cmd_pixels(args=None):
    from multiprocessing import Pool
    ensure_cache()
    fr = load_frames()
    fr = fr[fr["exists"]]
    done = set(load_pixels()["id"].tolist())
    jobs = [(int(i), p) for i, p in zip(fr["id"], fr["path"]) if int(i) not in done]
    print(f"[pixels] {len(fr)} frames with a file, {len(done)} cached, {len(jobs)} to compute")
    if jobs:
        new = not os.path.exists(PIXELS_CSV)
        t0 = time.time()
        with open(PIXELS_CSV, "a", newline="") as f, Pool(PIXEL_WORKERS) as pool:
            w = csv.DictWriter(f, fieldnames=PIXEL_COLS)
            if new:
                w.writeheader()
            for n, row in enumerate(pool.imap(pixel_features, jobs, chunksize=64), 1):
                w.writerow(row)
                if n % 2000 == 0:
                    f.flush()
                    print(f"   {n}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)
    px = load_pixels()
    print(f"[pixels] {len(px)} rows in {PIXELS_CSV}; unreadable: {int((~_flag(px, 'readable')).sum())}, "
          f"no_imagery: {int(_flag(px, 'no_imagery').sum())} "
          f"(byte-identical placeholder: {int((px['md5'] == PLACEHOLDER_MD5).sum())})")


def load_features():
    """frames + pixels + CLIP scores (recomputed from cached embeddings) + labels."""
    fr = load_frames()
    px = load_pixels()
    ids, emb = load_embeddings()
    if len(ids) == 0:
        sys.exit("no CLIP shards - run `clip` first")
    if len(px) == 0:
        sys.exit("no pixels.csv - run `pixels` first")
    df = fr.merge(clip_scores(ids, emb), on="id", how="left").merge(px, on="id", how="left")
    df["readable"] = _flag(df, "readable")
    df["no_imagery"] = _flag(df, "no_imagery")
    df = df.merge(load_labels(), on="filename", how="left")
    have = df["exists"] & df["readable"]
    n_clip = int((have & df["road_prob"].isna()).sum())
    n_px = int((df["exists"] & df["md5"].isna()).sum())
    if n_clip or n_px:
        print(f"WARNING: features incomplete (no pixels: {n_px}, no CLIP: {n_clip}) "
              "- rerun `pixels` / `clip`")
    return df


def dup_report(df, pairs, T=THRESHOLDS, examples=10, seed=0):
    n_clusters = int(df["dup_cluster"].dropna().nunique())
    print(f"[dups] matched pairs: {len(pairs)}, clusters: {n_clusters}, "
          f"frames in clusters: {int(df['dup_cluster'].notna().sum())}, "
          f"frames marked duplicate: {int(df['dup_of'].notna().sum())}")
    if len(pairs) == 0:
        return
    sizes = df["dup_cluster"].dropna().value_counts()
    dist = sizes.value_counts().sort_index()
    print("       cluster sizes (size: count): " + ", ".join(f"{s}: {c}" for s, c in dist.items()))
    names = {"img": f"<= {T['dup_img_m']:g} m + CLIP cosine >= {T['dup_img_cos']:g}",
             "spot": f"<= {T['dup_spot_m']:g} m",
             "pano": f"same pano_id + CLIP cosine >= {T['dup_pano_cos']:g}"}
    for k, r in enumerate(DUP_RULES):
        sub = pairs[pairs["rule"] == r]
        alone, _ = cluster_dups(df, sub)
        upto, _ = cluster_dups(df, pairs[pairs["rule"].isin(DUP_RULES[:k + 1])])
        print(f"  rule {r} ({names[r]}, heading diff <= {T['dup_heading_max_deg']:g}): {len(sub)} pairs; "
              f"duplicates with this rule alone: {int(alone.notna().sum())}; "
              f"cumulative with earlier rules: {int(upto.notna().sum())}")
        ex = sub.sample(min(examples, len(sub)), random_state=seed).sort_values("id_a")
        for _, p in ex.iterrows():
            print(f"      {int(p.id_a):>6} ~ {int(p.id_b):<6} dist={p.dist_m:6.2f} m  "
                  f"dhead={p.heading_diff:5.1f}  cos={p.cos:.4f}  hamming={int(p.hamming):2d}  "
                  f"same_pano={bool(p.same_pano)}")


def cmd_dups(args=None):
    df = load_features()
    out, pairs = decide(df, emb=aligned_embeddings(df))
    pairs.to_csv(DUP_PAIRS_CSV, index=False, float_format="%.3f")
    print(f"[dups] pairs -> {DUP_PAIRS_CSV}")
    dup_report(out, pairs)


def labelled_masks(df):
    lab = df["manual_rqi"]
    return lab.notna() & (lab <= 4), lab.notna() & (lab > 4)


def cmd_decide(args=None):
    df = load_features()
    out, pairs = decide(df, emb=aligned_embeddings(df))
    pairs.to_csv(DUP_PAIRS_CSV, index=False, float_format="%.3f")
    cols = (["id", "filename", "latitude", "longitude", "heading", "pano_id", "capture_date",
             "dino_rqi_score", "dino_score", "manual_rqi", "exists", "readable", "road_prob"]
            + P_COLS + [c for c in PIXEL_COLS if c not in ("id", "readable")]
            + ["usable", "reasons", "dup_of", "dup_cluster"])
    out[cols].to_csv(QUALITY_CSV, index=False, float_format="%.9g")
    print(f"[decide] {len(out)} rows -> {QUALITY_CSV}")

    ok14, ok5 = labelled_masks(out)
    n, n14, n5 = len(out), int(ok14.sum()), int(ok5.sum())
    print(f"  total {n}   usable {int(out['usable'].sum())}   unusable {int((~out['usable']).sum())} "
          f"({(~out['usable']).mean():.1%})")
    print(f"  labelled RQI 1-4 mapped to DB: {n14}   labelled RQI 5: {n5}")
    print(f"  {'reason':<15}{'frames':>8}{'only this':>11}{'RQI1-4 flagged':>18}{'RQI5 flagged':>16}")
    rs = out["reasons"].astype(str)
    for r in REASONS:
        m = rs.str.split("|").apply(lambda x: r in x)
        print(f"  {r:<15}{int(m.sum()):>8}{int((rs == r).sum()):>11}"
              f"{int((m & ok14).sum()):>9} ({(m & ok14).sum() / max(n14, 1):6.2%})"
              f"{int((m & ok5).sum()):>8} ({(m & ok5).sum() / max(n5, 1):6.1%})")
    bad = ~out["usable"]
    nd = bad & (rs != "duplicate")
    print(f"  {'ANY':<15}{int(bad.sum()):>8}{'':>11}"
          f"{int((bad & ok14).sum()):>9} ({(bad & ok14).sum() / max(n14, 1):6.2%})"
          f"{int((bad & ok5).sum()):>8} ({(bad & ok5).sum() / max(n5, 1):6.1%})")
    print(f"  {'ANY non-dup':<15}{int(nd.sum()):>8}{'':>11}"
          f"{int((nd & ok14).sum()):>9} ({(nd & ok14).sum() / max(n14, 1):6.2%})"
          f"{int((nd & ok5).sum()):>8} ({(nd & ok5).sum() / max(n5, 1):6.1%})")
    caos = out["pano_id"].fillna("").str.startswith("CAoS")
    print(f"  CAoS (user photosphere) frames: {int(caos.sum())}, flagged: {int((caos & bad).sum())} "
          f"(hood: {int((caos & rs.str.contains('hood')).sum())})")
    return out


def cmd_calibrate(args=None):
    df = load_features()
    live = df["exists"] & df["readable"] & ~df["no_imagery"]
    df = df[live]
    ok14, _ = labelled_masks(df)
    lab = df[ok14]
    print(f"[calibrate] frames with a real picture: {len(df)}; labelled RQI 1-4 among them: {len(lab)}")
    lo_q = [0.1, 0.5, 1, 2, 5, 50]
    hi_q = [50, 95, 98, 99, 99.5, 99.9]
    cand = {
        "road_prob": ("lt", [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]),
        "brightness": ("lt", [30, 40, 45, 50, 60, 70]),
        "dark_frac": ("gt", [0.3, 0.4, 0.5, 0.6, 0.7]),
        "blur": ("lt", [20, 50, 100, 200]),
        "blur_full": ("lt", [250, 300, 350, 380, 420, 500]),
        "sharp_p90": ("lt", [400, 600, 700, 730, 800, 900]),
    }
    for c in P_COLS:
        cand[c] = ("lt", [0.05, 0.1, 0.2, 0.3]) if c == "p_road" else ("ge", [0.3, 0.5, 0.7, 0.9])
    feats = ["road_prob"] + P_COLS + ["brightness", "dark_frac", "blur", "blur_full", "sharp_p90"]
    for f in feats:
        direction, thr = cand[f]
        qs = lo_q if direction == "lt" else hi_q
        key = FEATURE_RULES.get(f, (None, None))[1]
        cur = f"   [current {key} = {THRESHOLDS[key]:g}]" if key else ""
        print(f"\n{f}  (flag when {direction} threshold){cur}")
        print("  quantile %      " + "".join(f"{q:>10g}" for q in qs))
        for name, d in (("labelled RQI 1-4", lab), ("all frames", df)):
            v = np.nanpercentile(d[f].to_numpy(float), qs)
            print(f"  {name:<16}" + "".join(f"{x:>10.4g}" for x in v))
        ops = {"lt": lambda s, t: s < t, "gt": lambda s, t: s > t, "ge": lambda s, t: s >= t}[direction]
        print("  flagged at      " + "  ".join(
            f"{direction} {t:g}: {int(ops(df[f], t).sum())} (lab {int(ops(lab[f], t).sum())})" for t in thr))
    both = (df["sharp_p90"] < THRESHOLDS["blur_sharp_p90_max"]) & (df["blur_full"] < THRESHOLDS["blur_full_max"])
    print(f"\nblur rule (sharp_p90 < {THRESHOLDS['blur_sharp_p90_max']:g} AND blur_full < "
          f"{THRESHOLDS['blur_full_max']:g}): {int(both.sum())} frames, labelled RQI 1-4: {int((both & ok14).sum())}")
    print("labelled RQI 1-4 0.5th percentile: sharp_p90 = "
          f"{np.nanpercentile(lab['sharp_p90'], 0.5):.1f}, blur_full = {np.nanpercentile(lab['blur_full'], 0.5):.1f}")


# ---------------------------------------------------------------------------
# Contact sheets
# ---------------------------------------------------------------------------
def load_quality():
    if not os.path.exists(QUALITY_CSV):
        sys.exit(f"{QUALITY_CSV} missing - run `decide` first")
    df = pd.read_csv(QUALITY_CSV, dtype={"pano_id": str, "md5": str, "dhash": str, "capture_date": str,
                                         "phash": str, "filename": str})
    df["reasons"] = df["reasons"].fillna("").astype(str)
    return df


def _tile(row, focus=None, blind=False):
    tw, th, bar = 300, 200, (20 if blind else 48)
    tile = np.zeros((th + bar, tw, 3), np.uint8)
    img = cv2.imread(os.path.join(IMAGE_DIR, str(row["filename"])))
    if img is None:
        tile[:th] = 60
        cv2.putText(tile, "missing image", (70, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
    else:
        tile[:th] = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)

    def g(c, fmt):
        v = row.get(c)
        return "-" if v is None or pd.isna(v) else format(float(v), fmt)

    cats = [(c, row.get(f"p_{c}")) for c in CATEGORIES if c != "road"]
    cats = [(c, v) for c, v in cats if v is not None and not pd.isna(v)]
    top = max(cats, key=lambda x: x[1]) if cats else ("-", float("nan"))
    lab = "" if pd.isna(row.get("manual_rqi")) else f" L{float(row['manual_rqi']):g}"
    lines = [
        f"id {int(row['id'])}{lab} dino {g('dino_score', '.1f')} road {g('road_prob', '.2f')} pR {g('p_road', '.2f')}",
        f"br {g('brightness', '.0f')} dk {g('dark_frac', '.2f')} sp90 {g('sharp_p90', '.0f')} "
        f"bF {g('blur_full', '.0f')} b {g('blur', '.0f')}",
        (row["reasons"] or "usable")[:30] + f" {top[0][:7]} {top[1]:.2f}"
        + ("" if pd.isna(row.get("dup_of")) else f" >{int(row['dup_of'])}"),
    ]
    if blind:   # unbiased review: the id only, no scores, labels or reasons
        lines = [f"id {int(row['id'])}"]
    if focus and not blind and focus not in ("road_prob", "p_road", "brightness", "dark_frac", "sharp_p90", "blur_full", "blur"):
        lines[1] = f"{focus} {g(focus, '.3f')} " + lines[1][:28]
    for i, text in enumerate(lines):
        cv2.putText(tile, text, (3, th + 13 + i * 15), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                    (255, 255, 255), 1, cv2.LINE_AA)
    return tile


def write_sheets(rows, out_dir, stem, focus=None, cols=2, nrows_max=2, quality=70, blind=False):
    """rows (DataFrame) -> small JPEG sheets of cols x up to nrows_max tiles. Returns paths."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    recs = [r for _, r in rows.iterrows()]
    per = cols * nrows_max
    for page, i in enumerate(range(0, len(recs), per), 1):
        tiles = [_tile(r, focus, blind) for r in recs[i: i + per]]
        th, tw = tiles[0].shape[:2]
        nrows = (len(tiles) + cols - 1) // cols
        sheet = np.full((nrows * th + (nrows + 1) * 4, cols * tw + (cols + 1) * 4, 3), 255, np.uint8)
        for k, t in enumerate(tiles):
            r, c = divmod(k, cols)
            y, x = 4 + r * (th + 4), 4 + c * (tw + 4)
            sheet[y: y + th, x: x + tw] = t
        name = stem if len(recs) <= per else f"{stem}_p{page}"
        p = os.path.join(out_dir, name + ".jpg")
        cv2.imwrite(p, sheet, [cv2.IMWRITE_JPEG_QUALITY, quality])
        paths.append(p)
    return paths


def has_reason(df, reason):
    return df["reasons"].str.split("|").apply(lambda x: reason in x)


def borderline_rows(df, feature, n, T=THRESHOLDS):
    """The n frames nearest to the feature's threshold on the USABLE side."""
    direction, key = FEATURE_RULES[feature]
    t = T[key]
    live = df[~df["reasons"].str.contains("missing_image|no_imagery") & df[feature].notna()]
    side = live[live[feature] >= t] if direction == "lt" else \
        live[live[feature] <= t] if direction == "gt" else live[live[feature] < t]
    return side.assign(_d=(side[feature] - t).abs()).sort_values("_d").head(n).drop(columns="_d")


def cmd_sheet(args):
    df = load_quality()
    out_dir = args.out or SHEET_DIR
    focus = None
    if args.ids:
        ids = [int(x) for x in args.ids.split(",") if x.strip()]
        rows = df.set_index("id", drop=False).reindex(ids).dropna(subset=["id"])
        stem = f"ids_{ids[0]}_n{len(ids)}"
    elif args.reason:
        if args.reason not in REASONS:
            sys.exit(f"unknown reason {args.reason!r}; choose from {REASONS}")
        rows = df[has_reason(df, args.reason)]
        rows = rows.sample(min(args.n, len(rows)), random_state=args.seed).sort_values("id")
        stem = f"reason_{args.reason}_seed{args.seed}"
    elif args.borderline:
        if args.borderline not in FEATURE_RULES:
            sys.exit(f"unknown feature {args.borderline!r}; choose from {list(FEATURE_RULES)}")
        rows = borderline_rows(df, args.borderline, args.n)
        stem, focus = f"borderline_{args.borderline}", args.borderline
    else:
        sys.exit("give one of --ids, --reason, --borderline")
    if len(rows) == 0:
        print(f"[sheet] no frames for {stem}")
        return []
    paths = write_sheets(rows, out_dir, stem, focus, cols=args.cols, nrows_max=args.rows,
                         quality=args.quality, blind=args.blind)
    for p in paths:
        print(p)
    return paths


def cmd_candidates(args):
    """Review candidates as CSVs + printed id lists (no images): every flagged
    frame per reason, and the borderline frames per thresholded feature."""
    df = load_quality()
    out_dir = args.out or os.path.join(CACHE, "candidates")
    os.makedirs(out_dir, exist_ok=True)
    keep = ["id", "filename", "manual_rqi", "dino_score", "road_prob"] + P_COLS + [
        "brightness", "dark_frac", "blur", "blur_full", "sharp_p90", "reasons", "dup_of"]
    for r in REASONS:
        rows = df[has_reason(df, r)]
        if len(rows) == 0:
            continue
        p = os.path.join(out_dir, f"reason_{r}.csv")
        rows[keep].to_csv(p, index=False, float_format="%.4g")
        pick = rows.sample(min(args.n, len(rows)), random_state=args.seed).sort_values("id")
        print(f"{r}: {len(rows)} frames -> {p}")
        print(f"   sample (seed {args.seed}): " + ",".join(str(int(i)) for i in pick["id"]))
    for f in FEATURE_RULES:
        rows = borderline_rows(df, f, args.n)
        p = os.path.join(out_dir, f"borderline_{f}.csv")
        rows[keep].to_csv(p, index=False, float_format="%.4g")
        direction, key = FEATURE_RULES[f]
        print(f"borderline {f} (flag when {direction} {THRESHOLDS[key]:g}; nearest usable-side, "
              f"range {rows[f].min():.4g}..{rows[f].max():.4g}) -> {p}")
        print("   ids: " + ",".join(str(int(i)) for i in rows["id"]))


# ---------------------------------------------------------------------------
# DB write (dry run unless --commit)
# ---------------------------------------------------------------------------
UPDATE_SQL = (
    "UPDATE street_view_images s "
    "SET analysis_metadata = (COALESCE(s.analysis_metadata::jsonb, '{}'::jsonb) "
    "|| jsonb_build_object('frame_quality', v.fq::jsonb))::json "
    "FROM (VALUES %s) v(id, fq) WHERE s.id = v.id")
VERIFY_SQL = (
    "SELECT count(*) FILTER (WHERE (analysis_metadata::jsonb -> 'frame_quality') IS NOT NULL), "
    "count(*) FILTER (WHERE analysis_metadata::jsonb -> 'frame_quality' ->> 'usable' = 'false') "
    "FROM street_view_images")


def cmd_write(args):
    df = load_quality()
    payloads = [(int(r["id"]), json.dumps(build_payload(r), allow_nan=False))
                for _, r in df.iterrows()]
    n_bad = int((~df["usable"].astype(bool)).sum())
    print(f"[write] {len(payloads)} payloads (usable {len(payloads) - n_bad}, unusable {n_bad}), "
          f"version {PAYLOAD_VERSION}")
    rs = df["reasons"].str.split("|")
    print("        per reason: " + ", ".join(
        f"{r}={int(rs.apply(lambda x: r in x).sum())}" for r in REASONS))
    ex = pd.concat([df[df["usable"].astype(bool)].head(1), df[df["dup_of"].notna()].head(1),
                    df[~df["usable"].astype(bool) & df["dup_of"].isna()].head(1)])
    by_id = dict(payloads)
    print("        example payloads:")
    for i in ex["id"]:
        print(f"          id {int(i)}: {by_id[int(i)]}")
    print("        SQL (one transaction, execute_values page_size=1000, template (%s, %s)):")
    print("          " + UPDATE_SQL)
    print("        verification: " + VERIFY_SQL)

    if not args.commit:
        print("[write] DRY RUN - nothing written. Re-run with --commit --backup <fresh dump> to apply.")
        return
    b = args.backup
    if not b or not os.path.isfile(b) or os.path.getsize(b) == 0:
        sys.exit("[write] refusing to commit: --backup must point to an existing non-empty file")
    age = time.time() - os.path.getmtime(b)
    if age > 2 * 3600:
        sys.exit(f"[write] refusing to commit: backup {b} is {age / 3600:.1f} h old (max 2 h)")

    import psycopg2
    from psycopg2.extras import execute_values
    conn = psycopg2.connect(database_url())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM street_view_images WHERE id = ANY(%s)",
                        ([i for i, _ in payloads],))
            n_match = cur.fetchone()[0]
            execute_values(cur, UPDATE_SQL, payloads, template="(%s, %s)", page_size=1000)
            cur.execute(VERIFY_SQL)
            n_key, n_false = cur.fetchone()
            cur.execute("SELECT count(*) FROM street_view_images")
            n_rows = cur.fetchone()[0]
            if n_key != n_match or n_false != n_bad:
                conn.rollback()
                sys.exit(f"[write] verification failed (rows with key {n_key}, expected {n_match}; "
                         f"usable=false {n_false}, expected {n_bad}) - ROLLED BACK")
        conn.commit()
        print(f"[write] COMMITTED: {n_key}/{n_rows} rows have frame_quality, usable=false: {n_false}")
        if n_rows != n_key:
            print(f"[write] note: {n_rows - n_key} DB rows are newer than frames.csv and have no "
                  "frame_quality - rerun `all`")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cmd_all(args=None):
    cmd_manifest()
    cmd_clip()
    cmd_pixels()
    cmd_dups()
    cmd_decide()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("manifest", cmd_manifest), ("clip", cmd_clip), ("pixels", cmd_pixels),
                     ("dups", cmd_dups), ("decide", cmd_decide), ("calibrate", cmd_calibrate),
                     ("all", cmd_all)):
        sub.add_parser(name).set_defaults(fn=fn)
    s = sub.add_parser("sheet")
    s.add_argument("--ids")
    s.add_argument("--reason")
    s.add_argument("--borderline")
    s.add_argument("--n", type=int, default=12)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--cols", type=int, default=2)
    s.add_argument("--rows", type=int, default=2)
    s.add_argument("--quality", type=int, default=70)
    s.add_argument("--blind", action="store_true",
                   help="tiles show the id only (no scores/reasons) for an unbiased review")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_sheet)
    c = sub.add_parser("candidates")
    c.add_argument("--n", type=int, default=12)
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--out")
    c.set_defaults(fn=cmd_candidates)
    w = sub.add_parser("write")
    w.add_argument("--commit", action="store_true")
    w.add_argument("--backup")
    w.set_defaults(fn=cmd_write)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
