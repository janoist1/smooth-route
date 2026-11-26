"""
VLM second opinion on the map's least confident non-Budapest segments (T-69).

The Era 9 candidate (champion score + VLM attributes, ml/vlm_heads.py) beat
the champion by +0.031 QWK but needs a VLM call per frame. Here it runs
offline, as a second opinion, on the frames of the lowest-confidence
segments outside Budapest (the candidate did not help Budapest). Nothing the
map shows changes: results go to analysis_metadata.vlm_attrs / vlm_score /
vlm_rqi only, and dino_* / road_segments are never written.

    python ml/vlm_second_opinion.py pick [--frames 250]   # segments + frames
    python ml/vlm_second_opinion.py prepare               # blinded batches
    python ml/vlm_second_opinion.py apply                 # features + candidate
    python ml/vlm_second_opinion.py store                 # DB write (pg_dump first!)
    python ml/vlm_second_opinion.py report                # class changes + sample

Attributes come from the identical Era 9 prompt (ml/vlm_attribute_prompt.md)
with the same 12 anchors, filled in by Fable subagents that see only their
batch's hard-linked images under random ids.
"""
import argparse
import csv
import json
import os
import random
import sys

ML = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ML)
sys.path.insert(0, ML)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import numpy as np  # noqa: E402

from vlm_attributes import (BASE as ATT_BASE, MODEL_COLUMNS, encode,  # noqa: E402
                            parse_jsonl, validate)

OUT = os.path.join(ROOT, "data", "vlm", "second_opinion")
PICK = os.path.join(OUT, "_pick.csv")
KEY = os.path.join(OUT, "_key.csv")
RESULT = os.path.join(OUT, "result.csv")
CANDIDATE = os.path.join(ML, "cache", "rqi_model_vlm_candidate.joblib")
BATCH = 20
SEED = 69


def _bp(lat, lon):
    """Budapest (VII–VIII) bounding box; Budaörs/Törökbálint lie west of 18.98."""
    return lon > 18.98 and lat > 47.42


def pick(n_frames, extend=False):
    from sqlalchemy import text

    from app.core.database import SessionLocal
    from app.services.segment_read import frame_ids_on_segment

    db = SessionLocal()
    segs = db.execute(text(
        "SELECT id, confidence, n_images, rqi, score, road_name, highway, "
        "ST_Y(ST_Centroid(geom)) lat, ST_X(ST_Centroid(geom)) lon "
        "FROM road_segments WHERE n_images > 0 ORDER BY confidence, id")).all()
    labelled = {r[0] for r in db.execute(text(
        "SELECT image_filename FROM training_data")).all()}
    rows, used, done_segs = [], set(), set()
    if extend:  # next segments after the first pick; also skip everything east of 18.98
        old = _read(PICK)
        used = {int(r["image_id"]) for r in old}
        done_segs = {r["segment_id"] for r in old}
    for s in segs:
        if _bp(s.lat, s.lon) or s.id in done_segs or (extend and s.lon > 18.98):
            continue
        ids = [i for i in frame_ids_on_segment(db, s.id) if i not in used]
        if not ids:
            continue
        meta = db.execute(text(
            "SELECT id, image_url, latitude, longitude, dino_rqi_score, "
            "analysis_metadata->>'dino_score' ds FROM street_view_images "
            "WHERE id = ANY(:ids)"), {"ids": ids}).all()
        for m in meta:
            fn = os.path.basename(m.image_url or "")
            if not fn or not os.path.isfile(os.path.join(ROOT, "data", "images", fn)):
                continue
            used.add(m.id)
            rows.append({"segment_id": s.id, "seg_confidence": round(s.confidence, 3),
                         "seg_rqi": s.rqi, "seg_score": s.score, "road": s.road_name or "",
                         "highway": s.highway or "", "image_id": m.id, "filename": fn,
                         "lat": m.latitude, "lon": m.longitude,
                         "dino_score": m.ds if m.ds is not None else m.dino_rqi_score,
                         "labelled": int(fn in labelled)})
        if len([r for r in rows if not r["labelled"]]) >= n_frames:
            break
    os.makedirs(OUT, exist_ok=True)
    if extend:
        with open(PICK, "a", newline="") as fh:
            csv.DictWriter(fh, fieldnames=list(rows[0])).writerows(rows)
    else:
        with open(PICK, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    todo = [r for r in rows if not r["labelled"]]
    print(f"{len({r['segment_id'] for r in rows})} segments, {len(rows)} frames "
          f"({len(todo)} to rate, {len(rows) - len(todo)} human-labelled kept as is); "
          f"segment confidence {rows[0]['seg_confidence']}–{rows[-1]['seg_confidence']}")


def _read(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def prepare(extend=False):
    if os.path.exists(KEY) and not extend:
        sys.exit(f"{KEY} exists — refusing to re-blind")
    old = _read(KEY) if extend else []
    seen = {k["image_id"] for k in old}
    todo = [r for r in _read(PICK) if r["labelled"] == "0" and r["image_id"] not in seen]
    rng = random.Random(SEED + len(old))
    rng.shuffle(todo)
    key = list(old)
    first = len({k["batch"] for k in old})
    for b in range(0, len(todo), BATCH):
        name = f"s{first + b // BATCH:02d}"
        d = os.path.join(OUT, "imgs", name)
        os.makedirs(d)
        for r in todo[b:b + BATCH]:
            rid = f"img_{rng.randrange(10**5):05d}"
            while any(k["id"] == rid for k in key):
                rid = f"img_{rng.randrange(10**5):05d}"
            os.link(os.path.join(ROOT, "data", "images", r["filename"]),
                    os.path.join(d, rid + ".jpg"))
            key.append({"id": rid, "batch": name, "image_id": r["image_id"],
                        "filename": r["filename"]})
    os.makedirs(os.path.join(OUT, "out"), exist_ok=True)
    with open(KEY, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(key[0]))
        w.writeheader()
        w.writerows(key)
    prompts(sorted({k["batch"] for k in key[len(old):]}))
    print(f"{len(key)} frames in {len(set(k['batch'] for k in key))} batches -> {OUT}/imgs")


def prompts(batches):
    """Era 9 prompt, verbatim, with the same 12 anchors (kept in their own dir)."""
    tpl = open(os.path.join(ML, "vlm_attribute_prompt.md")).read()
    adir = os.path.join(ATT_BASE, "imgs", "anchors")
    calib = (f"1. Calibrate first: view ALL 12 anchor images in {adir} with "
             f"Read (list them with `ls {adir}`). The file name "
             "anchor_<RQI>_<k>.jpg gives an expert's RQI (3 per class). Note "
             "what separates neighbouring classes in this expert's style, "
             "especially 1 vs 2 and 2 vs 3. Write no lines for anchors.")
    os.makedirs(os.path.join(OUT, "prompts"), exist_ok=True)
    for b in batches:
        idir = os.path.join(OUT, "imgs", b)
        out = os.path.join(OUT, "out", b + ".jsonl")
        allowed = f"the images in {idir}, your output file {out}, and the anchors in {adir}"
        txt = (tpl.replace("{CALIBRATION_STEP}", calib).replace("{IMAGE_DIR}", idir)
               .replace("{OUT}", out).replace("{N}", str(len(os.listdir(idir))))
               .replace("{ALLOWED_FILES}", allowed))
        with open(os.path.join(OUT, "prompts", b + ".md"), "w") as fh:
            fh.write(txt)


def _attributes():
    key = {k["id"]: k for k in _read(KEY)}
    att = {}
    for f in sorted(os.listdir(os.path.join(OUT, "out"))):
        df, _ = parse_jsonl(os.path.join(OUT, "out", f))
        for rec in df.to_dict("records"):
            if rec.get("id") in key and not validate(rec):
                att[key[rec["id"]]["image_id"]] = rec
    return key, att


def apply():
    import joblib
    import pandas as pd

    from app.services.dino_service import DinoInferenceService

    key, att = _attributes()
    art = joblib.load(CANDIDATE)
    svc = DinoInferenceService()
    svc.load_model()  # champion backbone; same recipe keys (cls+patch) as the candidate base
    names = MODEL_COLUMNS  # the column set the candidate was trained on (attribute_matrix)
    rows = []
    for k in key.values():
        rec = att.get(k["image_id"])
        if rec is None:
            continue
        path = os.path.join(ROOT, "data", "images", k["filename"])
        feat = svc.extract_features(path)  # (1, 768) cls+patch, exactly as the champion
        A, n = encode(pd.DataFrame([rec]))
        a = np.array([[A[0, n.index(c)] if c in n else 0.0 for c in names]])
        raw = float(art["pipeline"].predict(np.hstack([feat, a]))[0])
        vlm_rqi = int(np.digitize(raw, art["thresholds"]) + 1)  # severity
        champ_raw = svc._to_raw(svc.score_from_features(feat))
        rows.append({"image_id": int(k["image_id"]), "filename": k["filename"],
                     "vlm_raw": round(raw, 4), "vlm_sev": vlm_rqi,
                     "dino_raw": round(champ_raw, 4),
                     "dino_sev": int(np.digitize(champ_raw, svc.thresholds) + 1),
                     "vlm_score": round(float(svc._to_canonical(raw)), 4),
                     "vlm_rqi": int(svc._to_canonical(vlm_rqi)),
                     "attrs": json.dumps(rec, ensure_ascii=False)})
    with open(RESULT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} frames scored ({len(key) - len(rows)} without valid attributes) -> {RESULT}")


def store():
    from sqlalchemy import text

    from app.core.database import SessionLocal

    db = SessionLocal()
    n = 0
    for r in _read(RESULT):
        attrs = json.loads(r["attrs"])
        attrs.pop("id", None)
        db.execute(text(
            "UPDATE street_view_images SET analysis_metadata = "
            "(COALESCE(analysis_metadata::jsonb, '{}'::jsonb) || jsonb_build_object("
            "'vlm_attrs', CAST(:a AS jsonb), 'vlm_score', CAST(:s AS double precision), "
            "'vlm_rqi', CAST(:q AS integer), 'vlm_model', 'era9-stack-vlm'))::json "
            "WHERE id = :id"),
            {"a": json.dumps(attrs, ensure_ascii=False), "s": float(r["vlm_score"]),
             "q": int(r["vlm_rqi"]), "id": int(r["image_id"])})
        n += 1
    db.commit()
    print(f"stored vlm_attrs/vlm_score/vlm_rqi on {n} frames (dino_* untouched)")


def _zone(lon):
    """east_of_18.98 = Budapest's southern outer districts and the agglomeration
    (Csepel/Soroksár/Dunaharaszti/M4): segment confidence ordering picked them
    because the Budapest test above only excludes VII–VIII-type inner city."""
    return "east_of_18.98" if lon > 18.98 else "rest"


def meta_road(pick_rows, sid):
    p = next(p for p in pick_rows if p["segment_id"] == sid)
    return f"{p['road']} ({p['highway']})"


def report():
    from app.services.segment_aggregation import load_config

    cfg = load_config()
    pick_rows = _read(PICK)
    res = {int(r["image_id"]): r for r in _read(RESULT)}
    from app.services.dino_service import DinoInferenceService
    svc = DinoInferenceService()
    svc.load_model()

    # frames
    lon = {int(p["image_id"]): float(p["lon"]) for p in pick_rows}
    for zone in ("rest", "east_of_18.98"):
        zr = [r for r in res.values() if _zone(lon[int(r["image_id"])]) == zone]
        zc = [r for r in zr if r["vlm_sev"] != r["dino_sev"]]
        zw = sum(int(r["vlm_sev"]) > int(r["dino_sev"]) for r in zc)
        print(f"  {zone}: {len(zr)} frames, {len(zc)} change ({zw} worse, {len(zc) - zw} better)")
    ch = [r for r in res.values() if r["vlm_sev"] != r["dino_sev"]]
    worse = sum(int(r["vlm_sev"]) > int(r["dino_sev"]) for r in ch)
    print(f"frames: {len(res)} rated, {len(ch)} change class "
          f"({worse} worse road, {len(ch) - worse} better road)")
    trans = {}
    for r in ch:
        k = (int(svc._to_canonical(int(r['dino_sev']))), int(r["vlm_rqi"]))
        trans[k] = trans.get(k, 0) + 1
    print("  canonical class DINO -> VLM:", dict(sorted(trans.items(), key=lambda x: -x[1])))

    # segments: the builder's own aggregation (aggregate_frames), run twice on
    # the same frames — once as the map has them, once with the VLM reading
    # substituted where we have one (P(bad) from the champion's calibrator
    # applied to the VLM score: an approximation, the candidate has none).
    import datetime as dt

    from sqlalchemy import text

    from app.core.database import SessionLocal
    from app.services.segment_aggregation import FrameObs, aggregate_frames, frame_p_bad, frame_score

    db = SessionLocal()
    ids = [int(p["image_id"]) for p in pick_rows]
    meta = {r.id: r for r in db.execute(text(
        "SELECT id, dino_rqi_score, capture_date, analysis_metadata FROM street_view_images "
        "WHERE id = ANY(:ids)"), {"ids": ids}).all()}
    seg_db = {r.id: r for r in db.execute(text(
        "SELECT id, rqi, confidence FROM road_segments WHERE id = ANY(:ids)"),
        {"ids": list({p["segment_id"] for p in pick_rows})}).all()}
    by_seg = {}
    for p in pick_rows:
        by_seg.setdefault(p["segment_id"], []).append(int(p["image_id"]))
    today = dt.date.today()
    seg_rows, same_as_db = [], 0
    for sid, fids in by_seg.items():
        d_obs, v_obs = [], []
        for fid in fids:
            m = meta[fid]
            sc = frame_score(m.dino_rqi_score, m.analysis_metadata)
            if sc is None:
                continue
            pb = frame_p_bad(m.dino_rqi_score, m.analysis_metadata, cfg.scale)
            d_obs.append(FrameObs(sc, pb, m.capture_date))
            r = res.get(fid)
            if r:
                vs = float(r["vlm_score"])
                v_obs.append(FrameObs(vs, svc.p_bad_from_score(vs), m.capture_date))
            else:
                v_obs.append(FrameObs(sc, pb, m.capture_date))
        if not d_obs:
            continue
        d, v = aggregate_frames(d_obs, cfg, today), aggregate_frames(v_obs, cfg, today)
        same_as_db += d.rqi == seg_db[sid].rqi
        seg_rows.append((sid, meta_road(pick_rows, sid), len(d_obs),
                         sum(f in res for f in fids), seg_db[sid].rqi, d.rqi, v.rqi,
                         round(d.score, 2), round(v.score, 2), round(d.confidence, 2),
                         round(v.confidence, 2)))
    print(f"segments: {len(seg_rows)} (recomputed class = map class on {same_as_db})")
    zone_of = {p["segment_id"]: _zone(float(p["lon"])) for p in pick_rows}
    for zone in ("rest", "east_of_18.98"):
        zr = [r for r in seg_rows if zone_of[r[0]] == zone and r[3] > 0]
        changed = [r for r in zr if r[5] != r[6]]
        up = sum(r[6] > r[5] for r in changed)
        print(f"  {zone}: {len(zr)} segments with VLM frames, {len(changed)} change class: "
              f"{up} better road, {len(changed) - up} worse (canonical 5 = Kiváló); moves: "
              + ", ".join(f"{a}->{b}: {sum(1 for r in changed if (r[5], r[6]) == (a, b))}"
                          for a, b in sorted({(r[5], r[6]) for r in changed})))
    rng = random.Random(SEED)
    sample = rng.sample(ch, min(10, len(ch)))
    path = os.path.join(OUT, "changed_sample.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["image_id", "filename", "dino_rqi", "vlm_rqi", "dino_score", "vlm_score",
                    "vlm_own_guess_canonical", "vlm_notes", "key_attrs"])
        for r in sample:
            a = json.loads(r["attrs"])
            w.writerow([r["image_id"], r["filename"],
                        int(svc._to_canonical(int(r["dino_sev"]))), r["vlm_rqi"],
                        round(svc._to_canonical(float(r["dino_raw"])), 2), r["vlm_score"],
                        int(svc._to_canonical(int(a.get("rqi_guess")))), a.get("notes", ""),
                        "; ".join(f"{k}={a.get(k)}" for k in
                                  ("surface", "cracks", "patches", "potholes", "ravelling",
                                   "edge_damage", "lighting", "wet"))])
    seg_path = os.path.join(OUT, "segments.csv")
    with open(seg_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["segment_id", "road", "n_frames", "n_vlm", "map_rqi_db", "map_rqi",
                    "vlm_rqi", "map_score", "vlm_score", "map_conf", "vlm_conf"])
        w.writerows(seg_rows)
    print(f"sample -> {os.path.relpath(path, ROOT)}; segments -> {os.path.relpath(seg_path, ROOT)}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["prompts"]:
        prompts(sorted(os.listdir(os.path.join(OUT, "imgs"))))
        sys.exit()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pick", "prepare", "apply", "store", "report"])
    ap.add_argument("--frames", type=int, default=250)
    ap.add_argument("--extend", action="store_true",
                    help="add the next segments/batches after an earlier pick")
    a = ap.parse_args()
    {"pick": lambda: pick(a.frames, a.extend), "prepare": lambda: prepare(a.extend), "apply": apply,
     "store": store, "report": report}[a.cmd]()
