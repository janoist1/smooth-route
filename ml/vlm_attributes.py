#!/usr/bin/env python3
"""
VLM attribute extraction (Era 9): blinded batches, prompts, status, merge.

The VLM (Claude "fable" subagents viewing images with the Read tool) is used as
a STRUCTURED FEATURE EXTRACTOR, not as a labeller: each frame gets a fixed set
of categorical pavement attributes (+ an rqi_guess) as one JSON line. The
prompt is ml/vlm_attribute_prompt.md; every worker gets the identical text.

Blinding (no label leakage):
  - frames are hard-linked under random ids (img_XXXXX.jpg) into per-batch
    folders — the original filenames carry GPS + sequence numbers;
  - batches are a random shuffle of the dataset (mixed areas/classes);
  - workers may open only their batch images, the 12 calibration anchors
    (anchor_<RQI>_<k>.jpg — the only labels they ever see, as in the pilot
    rubric) and their own output file. The id -> filename key lives outside
    the worker folders;
  - the 12 anchor frames are themselves rated in batch b00 by a worker that
    sees NO anchors, so their rows are not contaminated by their own label.

Layout (data/ is gitignored):
  data/vlm/attributes/imgs/{anchors,pilot,b00..bNN}/   hard links
  data/vlm/attributes/prompts/<batch>.md                rendered prompts
  data/vlm/attributes/out/<batch>.jsonl                 worker output (resumable)
  data/vlm/attributes/_key.csv                          blind id -> filename
  ml/cache/vlm_attributes.csv                           merged (step `merge`)

Usage:
  python ml/vlm_attributes.py prepare      # once (refuses to overwrite)
  python ml/vlm_attributes.py status       # lines / validity per batch
  python ml/vlm_attributes.py anchor_free  # anchor twins -> anchor-free b00
  python ml/vlm_attributes.py pilot        # A-vs-B consistency on the pilot
  python ml/vlm_attributes.py anchor_check # leakage + test-retest checks
  python ml/vlm_attributes.py merge        # -> ml/cache/vlm_attributes.csv
"""
import json
import math
import os
import random
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spatial_cv as S  # noqa: E402

ROOT = S.ROOT
CACHE = os.path.join(ROOT, "ml", "cache")
IMG_SRC = os.path.join(ROOT, "data", "images")
BASE = os.path.realpath(os.path.join(ROOT, "data", "vlm", "attributes"))
KEY = os.path.join(BASE, "_key.csv")
PROMPT = os.path.join(ROOT, "ml", "vlm_attribute_prompt.md")
MERGED = os.path.join(CACHE, "vlm_attributes.csv")

N_BATCHES = 16
N_PILOT = 30
SEED = 42

# Fixed schema: key -> allowed values (ordered best..worst where ordinal).
SCHEMA = {
    "road_visible": ["yes", "partial", "no"],
    "road_type": ["motorway", "urban_main", "urban_residential", "rural_road",
                  "rural_lane", "other"],
    "surface": ["asphalt", "concrete", "cobblestone", "unpaved", "mixed"],
    "cracks": ["none", "few_single", "many_longitudinal", "many_transverse",
               "alligator_local", "alligator_extensive"],
    "patches": ["none", "few", "many", "patchwork"],
    "potholes": ["none", "small_few", "small_many", "deep"],
    "ravelling": ["none", "some", "severe"],
    "edge_damage": ["none", "some", "severe"],
    "rutting": ["none", "some", "severe"],
    "markings": ["none_expected", "intact", "faded", "gone"],
    "lighting": ["normal", "dappled_shadow", "dark", "overexposed"],
    "wet": ["no", "yes"],
    "confidence": ["low", "medium", "high"],
}
NUMERIC = {"obstruction_pct": (0, 100), "rqi_guess": (1, 4)}
FIELDS = ["id"] + list(SCHEMA)[:12] + ["obstruction_pct", "rqi_guess",
                                       "confidence", "notes"]

# Ordinal severity used for encoding (unlisted categorical keys -> one-hot).
ORDINAL = {
    "road_visible": {"yes": 0, "partial": 1, "no": 2},
    "cracks": {"none": 0, "few_single": 1, "many_longitudinal": 2,
               "many_transverse": 2, "alligator_local": 3,
               "alligator_extensive": 4},
    "patches": {"none": 0, "few": 1, "many": 2, "patchwork": 3},
    "potholes": {"none": 0, "small_few": 1, "small_many": 2, "deep": 3},
    "ravelling": {"none": 0, "some": 1, "severe": 2},
    "edge_damage": {"none": 0, "some": 1, "severe": 2},
    "rutting": {"none": 0, "some": 1, "severe": 2},
    "markings": {"none_expected": 0, "intact": 0, "faded": 1, "gone": 2},
    "wet": {"no": 0, "yes": 1},
    "confidence": {"low": 0, "medium": 1, "high": 2},
}
ONEHOT = ["road_type", "surface", "cracks", "markings", "lighting"]


def _dist_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    return 6371000 * math.hypot((lo2 - lo1) * math.cos((la1 + la2) / 2),
                                la2 - la1)


def dataset():
    from experiments import load
    feats, df = load("small")
    c = S.load_coords(df["image_filename"])
    df = df.assign(lat=c["lat"].values, lon=c["lon"].values,
                   area=c["area"].values)
    return feats, df


def champion_oof(feats, df):
    """Spatial OOF of the live recipe (cls+patch, SVR C=1), cached."""
    path = os.path.join(CACHE, "oof_champion_spatial.npz")
    if os.path.exists(path):
        z = np.load(path, allow_pickle=True)
        if list(z["files"]) == list(df["image_filename"]):
            return {k: z[k] for k in ("oof", "pred", "fold")}
    from sklearn.svm import SVR
    X = np.hstack([feats["cls"], feats["patch"]])
    y = df["manual_rqi"].values.astype(float)
    yc = df["rqi"].values.astype(int)
    g = S.grid_cells(df["lat"].values, df["lon"].values)
    res = S.nested_spatial_cv(X, y, yc, g, lambda: SVR(C=1.0, gamma="scale",
                                                       epsilon=0.05))
    np.savez(path, files=np.array(df["image_filename"]), oof=res["oof"],
             pred=res["pred"], fold=res["fold"])
    return res


def prepare():
    if os.path.exists(KEY):
        sys.exit(f"{KEY} exists — refusing to re-blind (would orphan outputs)")
    rng = random.Random(SEED)
    feats, df = dataset()
    res = champion_oof(feats, df)
    df = df.assign(oof_pred=res["pred"])

    # 12 anchors: 3 per class, prototypical (champion OOF agrees), road clearly
    # detected, spread over areas and >= 300 m apart.
    anchors, chosen = [], []
    for c in (1, 2, 3, 4):
        pool = df[(df.rqi == c) & (df.oof_pred == c) & (df.is_road_prob > 0.85)]
        pool = pool.sample(frac=1, random_state=SEED + c)
        areas_used = set()
        # pass 1: distinct areas, >= 300 m apart; pass 2: any area, >= 150 m
        for strict, min_d in ((True, 300), (False, 150)):
            for _, r in pool.iterrows():
                if len([a for a in anchors if a[1] == c]) == 3:
                    break
                if r.image_filename in {a[0] for a in anchors}:
                    continue
                if strict and r.area in areas_used:
                    continue
                if all(_dist_m((r.lat, r.lon), q) >= min_d for q in chosen):
                    anchors.append((r.image_filename, c))
                    chosen.append((r.lat, r.lon))
                    areas_used.add(r.area)
    anchor_files = {f for f, _ in anchors}

    ids = rng.sample(range(10000, 99999), len(df) + N_PILOT)
    rest = df[~df.image_filename.isin(anchor_files)].sample(
        frac=1, random_state=SEED).image_filename.tolist()
    batches = {"b00": sorted(anchor_files)}
    for k in range(N_BATCHES):
        batches[f"b{k + 1:02d}"] = rest[k::N_BATCHES]
    # pilot: 30 frames stratified by class (8/8/7/7), from the non-anchor pool
    pil = []
    for c, n in zip((1, 2, 3, 4), (8, 8, 7, 7)):
        pil += df[(df.rqi == c) & ~df.image_filename.isin(anchor_files)].sample(
            n, random_state=SEED + 10 * c).image_filename.tolist()
    rng.shuffle(pil)
    batches["pilot"] = pil

    rows, it = [], iter(ids)
    for b, files in batches.items():
        d = os.path.join(BASE, "imgs", b)
        os.makedirs(d, exist_ok=True)
        for f in files:
            bid = f"img_{next(it)}"
            os.link(os.path.join(IMG_SRC, f), os.path.join(d, bid + ".jpg"))
            rows.append({"blind_id": bid, "image_filename": f, "batch": b})
    d = os.path.join(BASE, "imgs", "anchors")
    os.makedirs(d, exist_ok=True)
    cnt = {}
    for f, c in anchors:
        cnt[c] = cnt.get(c, 0) + 1
        os.link(os.path.join(IMG_SRC, f),
                os.path.join(d, f"anchor_{c}_{cnt[c]}.jpg"))
    os.makedirs(os.path.join(BASE, "out"), exist_ok=True)
    pd.DataFrame(rows).to_csv(KEY, index=False)
    pd.DataFrame(anchors, columns=["image_filename", "rqi"]).to_csv(
        os.path.join(BASE, "_anchors.csv"), index=False)
    render_prompts(batches)
    print({b: len(v) for b, v in batches.items()})


def anchor_free(min_d=50.0):
    """Move frames within min_d of an anchor into the anchor-free batch b00.

    Found during the run: consecutive frames ~10 m apart are often the SAME
    panorama (identical pixels), so a worker that saw anchor_1_2 could
    recognise its twin in a regular batch and copy the expert label. Every
    frame within min_d of an anchor is therefore re-rated in b00 (no anchors
    shown); merge() keeps the b00 row. Safe to run before b00 starts only.
    """
    key = pd.read_csv(KEY)
    if os.path.exists(os.path.join(BASE, "out", "b00.jsonl")):
        sys.exit("b00 already started — refusing to change it")
    co = S.load_coords(key.image_filename.drop_duplicates())
    co = co.set_index("image_filename")
    anc = pd.read_csv(os.path.join(BASE, "_anchors.csv"))
    have = set(key.loc[key.batch == "b00", "image_filename"])
    cand = key.loc[~key.batch.isin(["pilot", "b00"]), "image_filename"]
    add = []
    for f in cand:
        p = (co.loc[f, "lat"], co.loc[f, "lon"])
        if f not in have and any(
                _dist_m(p, (co.loc[a, "lat"], co.loc[a, "lon"])) < min_d
                for a in anc.image_filename):
            add.append(f)
    used = set(int(b[4:]) for b in key.blind_id)
    rng = random.Random(SEED + 1)
    free = [i for i in range(10000, 99999) if i not in used]
    ids = rng.sample(free, len(add))
    d = os.path.join(BASE, "imgs", "b00")
    rows = []
    for f, i in zip(add, ids):
        os.link(os.path.join(IMG_SRC, f), os.path.join(d, f"img_{i}.jpg"))
        rows.append({"blind_id": f"img_{i}", "image_filename": f,
                     "batch": "b00"})
    key = pd.concat([key, pd.DataFrame(rows)], ignore_index=True)
    key.to_csv(KEY, index=False)
    b00 = key.loc[key.batch == "b00", "image_filename"].tolist()
    render_prompts({"b00": b00})
    print(f"added {len(add)} anchor-neighbour frames; b00 now {len(b00)}")


def anchor_check():
    """Anchor-neighbour frames rated twice: with anchors (regular batch) and
    without (b00). If the regular rating agrees with the human label much more
    often, the anchors leaked their labels to nearby twins. Also measures the
    test-retest agreement of the attributes across workers."""
    from sklearn.metrics import cohen_kappa_score
    key = pd.read_csv(KEY)
    _, df = dataset()
    lab = df.set_index("image_filename")["rqi"]
    b00, _ = parse_jsonl(os.path.join(BASE, "out", "b00.jsonl"))
    b00 = b00.merge(key[key.batch == "b00"], left_on="id", right_on="blind_id")
    anc = set(pd.read_csv(os.path.join(BASE, "_anchors.csv")).image_filename)
    b00 = b00[~b00.image_filename.isin(anc)]
    reg = []
    for b in sorted(set(key.batch) - {"pilot", "b00"}):
        d, _ = parse_jsonl(os.path.join(BASE, "out", b + ".jsonl"))
        reg.append(d.merge(key[key.batch == b], left_on="id",
                           right_on="blind_id"))
    reg = pd.concat(reg)
    m = b00.merge(reg, on="image_filename", suffixes=("_free", "_anch"))
    h = m.image_filename.map(lab).values
    print(f"{len(m)} anchor-neighbour frames rated with and without anchors")
    for s in ("anch", "free"):
        g = m["rqi_guess_" + s].astype(int).values
        print(f"  rqi_guess {s}: exact vs human {np.mean(g == h):.2f}  QWK "
              f"{cohen_kappa_score(h, g, weights='quadratic'):.3f}  "
              f"mean {g.mean():.2f} (human {h.mean():.2f})")
    print("  attribute agreement with/without anchors (other worker): " +
          ", ".join(f"{k} {np.mean(m[k + '_free'] == m[k + '_anch']):.2f}"
                    for k in list(SCHEMA) + ["rqi_guess"]))
    # pilot frames were rated a second time in the full run (other worker)
    pa, _ = parse_jsonl(os.path.join(BASE, "out", "pilot_A.jsonl"))
    pa = pa.merge(key[key.batch == "pilot"], left_on="id", right_on="blind_id")
    mp = pa.merge(reg, on="image_filename", suffixes=("_p", "_r"))
    print(f"  pilot_A vs full-run worker on {len(mp)} frames: " + ", ".join(
        f"{k} {np.mean(mp[k + '_p'] == mp[k + '_r']):.2f}"
        for k in list(SCHEMA) + ["rqi_guess"]))


def render_prompts(batches):
    tpl = open(PROMPT).read()
    os.makedirs(os.path.join(BASE, "prompts"), exist_ok=True)
    adir = os.path.join(BASE, "imgs", "anchors")
    calib = (f"1. Calibrate first: view ALL 12 anchor images in {adir} with "
             f"Read (list them with `ls {adir}`). The file name "
             "anchor_<RQI>_<k>.jpg gives an expert's RQI (3 per class). Note "
             "what separates neighbouring classes in this expert's style, "
             "especially 1 vs 2 and 2 vs 3. Write no lines for anchors.")
    nocalib = ("1. (No calibration images for this batch — rely on the "
               "written scale.)")
    outs = {"pilot": ["pilot_A", "pilot_B"]}
    for b, files in batches.items():
        idir = os.path.join(BASE, "imgs", b)
        for name in outs.get(b, [b]):
            out = os.path.join(BASE, "out", name + ".jsonl")
            allowed = (f"the images in {idir}, your output file {out}"
                       + ("" if b == "b00" else f", and the anchors in {adir}"))
            txt = (tpl.replace("{CALIBRATION_STEP}",
                               nocalib if b == "b00" else calib)
                   .replace("{IMAGE_DIR}", idir).replace("{OUT}", out)
                   .replace("{N}", str(len(files)))
                   .replace("{ALLOWED_FILES}", allowed))
            with open(os.path.join(BASE, "prompts", name + ".md"), "w") as fh:
                fh.write(txt)


def parse_jsonl(path):
    """-> (DataFrame of valid rows, list of problems). Last line per id wins."""
    rows, bad = {}, []
    if not os.path.exists(path):
        return pd.DataFrame(columns=FIELDS), bad
    for n, line in enumerate(open(path), 1):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            bad.append(f"{os.path.basename(path)}:{n} not JSON")
            continue
        err = validate(r)
        if err:
            bad.append(f"{os.path.basename(path)}:{n} {err}")
            continue
        rows[r["id"]] = r
    return pd.DataFrame(list(rows.values()), columns=FIELDS), bad


def validate(r):
    if not str(r.get("id", "")).startswith("img_"):
        return "bad id"
    for k, vals in SCHEMA.items():
        if r.get(k) not in vals:
            return f"{k}={r.get(k)!r}"
    for k, (lo, hi) in NUMERIC.items():
        try:
            v = float(r.get(k))
        except (TypeError, ValueError):
            return f"{k}={r.get(k)!r}"
        if not lo <= v <= hi:
            return f"{k}={v}"
    return None


def status():
    key = pd.read_csv(KEY)
    for b, grp in key.groupby("batch"):
        for name in (["pilot_A", "pilot_B"] if b == "pilot" else [b]):
            df, bad = parse_jsonl(os.path.join(BASE, "out", name + ".jsonl"))
            ok = df["id"].isin(grp["blind_id"]).sum()
            extra = (~df["id"].isin(grp["blind_id"])).sum()
            print(f"{name:8s} {ok:4d}/{len(grp):4d} valid"
                  + (f"  {extra} foreign ids" if extra else "")
                  + (f"  {len(bad)} bad lines" if bad else ""))
            for p in bad[:5]:
                print("    ", p)


def pilot():
    from sklearn.metrics import cohen_kappa_score
    key = pd.read_csv(KEY).set_index("blind_id")
    _, df = dataset()
    lab = df.set_index("image_filename")["rqi"]
    a, _ = parse_jsonl(os.path.join(BASE, "out", "pilot_A.jsonl"))
    b, _ = parse_jsonl(os.path.join(BASE, "out", "pilot_B.jsonl"))
    m = a.merge(b, on="id", suffixes=("_a", "_b"))
    print(f"pilot: {len(a)} A, {len(b)} B, {len(m)} paired\n")
    print(f"{'attribute':16s} agree  kappa(A,B)")
    for k in list(SCHEMA) + ["rqi_guess", "obstruction_pct"]:
        x, y = m[k + "_a"].astype(str), m[k + "_b"].astype(str)
        kap = cohen_kappa_score(x, y) if len(set(x) | set(y)) > 1 else float("nan")
        print(f"{k:16s} {np.mean(x == y):5.2f}  {kap:6.2f}   "
              f"A={dict(x.value_counts())}")
    m["human"] = [lab[key.loc[i, "image_filename"]] for i in m["id"]]
    for s in ("a", "b"):
        g = m["rqi_guess_" + s].astype(int)
        print(f"rqi_guess {s.upper()} vs human: QWK "
              f"{cohen_kappa_score(m.human, g, weights='quadratic'):.3f}  "
              f"exact {np.mean(m.human == g):.2f}")
    avg = np.rint((m.rqi_guess_a.astype(float) + m.rqi_guess_b.astype(float)) / 2)
    print(f"A-B rqi_guess QWK {cohen_kappa_score(m.rqi_guess_a.astype(int), m.rqi_guess_b.astype(int), weights='quadratic'):.3f}"
          f"; mean(A,B) vs human QWK {cohen_kappa_score(m.human, avg.astype(int), weights='quadratic'):.3f}")


def merge():
    key = pd.read_csv(KEY)
    key = key[key.batch != "pilot"]
    parts, problems = [], []
    for b in sorted(key.batch.unique()):
        df, bad = parse_jsonl(os.path.join(BASE, "out", b + ".jsonl"))
        problems += bad
        parts.append(df.assign(batch=b))
    att = pd.concat(parts, ignore_index=True)
    att = att.merge(key, left_on=["id", "batch"],
                    right_on=["blind_id", "batch"], how="inner")
    missing = sorted(set(key.image_filename) - set(att.image_filename))
    att = att.drop(columns=["id"]).rename(columns={"blind_id": "vlm_blind_id",
                                                   "batch": "vlm_batch"})
    # anchor-free re-ratings (b00) supersede a frame's regular-batch row
    att["_pri"] = (att["vlm_batch"] == "b00").astype(int)
    n_sup = int(att.duplicated("image_filename", keep=False).sum() // 2)
    att = (att.sort_values(["image_filename", "_pri"])
           .drop_duplicates("image_filename", keep="last"))
    print(f"{n_sup} frames re-rated anchor-free (b00 row kept)")
    cols = ["image_filename", "vlm_blind_id", "vlm_batch"] + FIELDS[1:]
    att = att[cols].sort_values("image_filename")
    att.to_csv(MERGED, index=False)
    print(f"merged {len(att)} rows -> {os.path.relpath(MERGED, ROOT)}; "
          f"{len(missing)} frames missing, {len(problems)} bad lines")
    for p in problems[:10]:
        print("   ", p)
    return missing


# Fixed encoded-column list used by the Era 9 candidate artifact (encode()
# output minus one-hot levels rarer than 1 % in the 1903 labelled frames).
MODEL_COLUMNS = [
    "road_visible_ord", "cracks_ord", "patches_ord", "potholes_ord",
    "ravelling_ord", "edge_damage_ord", "rutting_ord", "markings_ord",
    "wet_ord", "confidence_ord", "obstruction_pct", "rqi_guess",
    "road_type=motorway", "road_type=urban_main",
    "road_type=urban_residential", "road_type=rural_road",
    "road_type=rural_lane", "surface=asphalt", "cracks=none",
    "cracks=few_single", "cracks=many_longitudinal", "cracks=many_transverse",
    "cracks=alligator_local", "markings=none_expected", "markings=intact",
    "markings=faded", "markings=gone", "lighting=normal",
    "lighting=dappled_shadow", "lighting=overexposed"]


def attribute_matrix(filenames, path=MERGED):
    """Encoded MODEL_COLUMNS for ``filenames`` (zeros where a frame has no
    VLM row — only frames outside the 1903 training set, e.g. RQI 5)."""
    att = pd.read_csv(path)
    A, names = encode(att)
    A = A[:, [names.index(c) for c in MODEL_COLUMNS]]
    pos = {f: i for i, f in enumerate(att["image_filename"])}
    out = np.zeros((len(filenames), len(MODEL_COLUMNS)))
    for r, f in enumerate(filenames):
        if f in pos:
            out[r] = A[pos[f]]
    return out


def encode(att):
    """Attribute DataFrame -> numeric matrix (ordinal + one-hot), names."""
    cols, names = [], []
    for k, mp in ORDINAL.items():
        cols.append(att[k].map(mp).astype(float).values)
        names.append(k + "_ord")
    for k in ("obstruction_pct", "rqi_guess"):
        cols.append(att[k].astype(float).values)
        names.append(k)
    for k in ONEHOT:
        for v in SCHEMA[k]:
            cols.append((att[k] == v).astype(float).values)
            names.append(f"{k}={v}")
    return np.stack(cols, 1), names


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"prepare": prepare, "anchor_free": anchor_free, "status": status,
     "pilot": pilot, "anchor_check": anchor_check,
     "merge": merge}[cmd]()
