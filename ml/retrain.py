#!/usr/bin/env python3
"""
One-command retrain: new owner labels -> features -> spatial gate -> candidate.

    .venv/bin/python ml/retrain.py            # or: make retrain

Steps (everything lands in ml/cache/retrain/<run>/; the shared caches and the
live ml/cache/rqi_model.joblib are never written):

  1. export    bash ml/export_labels.sh -> <run>/labels.csv. Labels arrive in
               the ML severity orientation (1 = best), whatever the canonical
               direction in shared/rqi_scale.json is (ml/rqi_scale.py).
  2. features  per labelled frame, reused in this order:
                 a. the current cache (feats_v2_small.npz + clip_v2.npz, by filename);
                 b. ml/cache/frame_feats_v2.npz (cls+patch by frame id, written by
                    the backend re-score) + road_prob from
                    analysis_metadata.frame_quality. Flip/crop/CLIP-embedding
                    views stay NaN for these rows: the champion recipe
                    (cls+patch) does not use them;
                 c. otherwise DINOv2 + CLIP on MPS, for these frames only.
  3. coords    ml/build_coords.py -> <run>/image_coords.csv
  4. fit       ml/save_model_v2.py (champion recipe) -> <run>/rqi_model_candidate.joblib
  5. gate      ml/evaluate_artifact.py on the candidate (official spatial CV).
  6. reports   - paired "do the new labels help?": the same spatial folds, the
                 same test frames, trained on old labels only vs on all labels
                 (cell bootstrap of the difference);
               - champion vs candidate on the NEW labels only (the champion
                 never saw them: a true holdout);
               - Budapest only (candidate OOF) and leave-Budapest-out.
  7. output    ml/cache/rqi_model_candidate.joblib + <run>/summary.md. Promotion
               stays a human decision: the command is printed, never run.

compare_candidates.py is NOT run: it compares feature/head recipes on fixed
data, and a same-recipe retrain would always show a zero difference there.
The paired old-vs-all-labels test is the matching question for a retrain.

Options: --labels CSV (skip the DB export), --min-new N (default 50; stop
early when fewer new labels), --force, --no-extract (fail instead of running
the GPU), --run-dir DIR.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ML = os.path.join(ROOT, "ml")
sys.path.insert(0, ML)
CACHE = os.path.join(ML, "cache")
CHAMPION = os.path.join(CACHE, "rqi_model.joblib")
CANDIDATE = os.path.join(CACHE, "rqi_model_candidate.joblib")
FRAME_FEATS = os.path.join(CACHE, "frame_feats_v2.npz")
PY = sys.executable
DINO_KEYS = ["cls", "patch", "cls_flip", "patch_flip", "cls_crop", "patch_crop"]
DIM = 384
BUDAPEST = "budapest"
# reuse frame_feats_v2.npz only if it reproduces the cache on overlapping frames
FRAME_FEATS_MAX_REL_DIFF = 0.02


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in ml/tests/test_retrain.py)
# ---------------------------------------------------------------------------
def build_manifest(labels, exists):
    """labels.csv -> dataset_v2-style manifest (image_filename, manual_rqi, rqi,
    tags, svi_id). Drops rows without a label / image and duplicate files."""
    df = labels[labels["manual_rqi"].notna()].copy()
    df = df.drop_duplicates("image_filename", keep="last")
    df["rqi"] = df["manual_rqi"].round().clip(1, 5).astype(int)
    df = df[[exists(f) for f in df["image_filename"]]]
    if "svi_id" not in df:
        df["svi_id"] = np.nan
    return df[["image_filename", "manual_rqi", "rqi", "tags", "svi_id"]].reset_index(drop=True)


def diff_labels(old, new):
    """old/new: DataFrames with image_filename + manual_rqi -> counts + new filenames."""
    o = old.set_index("image_filename")["manual_rqi"]
    n = new.set_index("image_filename")["manual_rqi"]
    common = o.index.intersection(n.index)
    changed = common[(o[common] - n[common]).abs() > 1e-9]
    return {"new": [f for f in n.index if f not in o.index],
            "changed": list(changed),
            "removed": [f for f in o.index if f not in n.index]}


def assemble_features(manifest, old, frame_feats=None, road_prob=None):
    """Per manifest row: DINO views + CLIP embedding + road_prob, and its source.

    old: {"files": [...], "feats": {key: [n, 384]}, "clip": [n, 512], "road_prob": [n]}
    frame_feats: {"ids": [...], "cls": [m, 384], "patch": [m, 384]} or None
    road_prob: {frame id: p} (e.g. analysis_metadata.frame_quality.road_prob)
    Returns (feats {key: array}, clip, road_prob array, source list, todo index list).
    """
    n = len(manifest)
    clip_dim = old["clip"].shape[1] if len(old["files"]) else 512
    feats = {k: np.full((n, DIM), np.nan, np.float32) for k in DINO_KEYS}
    clip = np.full((n, clip_dim), np.nan, np.float32)
    rp = np.full(n, np.nan)
    src, todo = [], []
    pos_old = {f: i for i, f in enumerate(old["files"])}
    pos_ff = {int(i): j for j, i in enumerate(frame_feats["ids"])} if frame_feats else {}
    road_prob = road_prob or {}
    for r, (f, sid) in enumerate(zip(manifest["image_filename"], manifest["svi_id"])):
        if f in pos_old:
            i = pos_old[f]
            for k in DINO_KEYS:
                feats[k][r] = old["feats"][k][i]
            clip[r] = old["clip"][i]
            rp[r] = old["road_prob"][i]
            src.append("cache")
            continue
        sid = None if sid is None or pd.isna(sid) else int(sid)
        if sid is not None and sid in pos_ff and sid in road_prob:
            j = pos_ff[sid]
            feats["cls"][r] = frame_feats["cls"][j]
            feats["patch"][r] = frame_feats["patch"][j]
            rp[r] = road_prob[sid]
            src.append("frame_feats")
            continue
        src.append("extract")
        todo.append(r)
    return feats, clip, rp, src, todo


def masked_nested_cv(X, y, yc, groups, make_model, train_mask):
    """ml/spatial_cv.nested_spatial_cv, but only rows with train_mask are used
    for fitting (outer and inner). Test folds stay the same for every mask, so
    two masks give a paired comparison on identical test frames."""
    import spatial_cv as S
    oof = np.zeros(len(y))
    pred = np.zeros(len(y), dtype=int)
    fold = np.zeros(len(y), dtype=int)
    for k, (tr, te) in enumerate(S.spatial_folds(yc, groups)):
        tr = tr[train_mask[tr]]
        oof[te] = S._fit_predict(make_model, X[tr], y[tr], X[te])
        ioof = np.zeros(len(tr))
        for itr, ite in S.spatial_folds(yc[tr], groups[tr], S.INNER_SPLITS):
            ioof[ite] = S._fit_predict(make_model, X[tr][itr], y[tr][itr], X[tr][ite])
        th = S.tune_thresholds(yc[tr], ioof)
        pred[te] = np.digitize(oof[te], th) + 1
        fold[te] = k
    return {"oof": oof, "pred": pred, "fold": fold}


def orientation_check(old, new, min_overlap=30, min_rho=0.5):
    """Do the exported labels run in the same direction as the cached ones?

    A canonical-scale flip (shared/rqi_scale.json) that the export does not
    convert back would silently invert every label. On frames present in both
    sets the labels must correlate strongly and positively.
    Returns (ok, spearman rho or None, overlap n)."""
    m = old[["image_filename", "manual_rqi"]].merge(
        new[["image_filename", "manual_rqi"]], on="image_filename")
    if len(m) < min_overlap:
        return True, None, len(m)
    rho = float(m["manual_rqi_x"].corr(m["manual_rqi_y"], method="spearman"))
    return rho >= min_rho, rho, len(m)


def verdict(gate_pass, delta, n_new=None, min_new=0):
    """Recommend promotion? Gate PASS, at least min_new new labels, and the new
    labels must not make the paired spatial CV worse (ΔQWK >= 0 and its 95% CI
    above -0.02). delta: {"qwk": (d, lo, hi), ...} or None (no new labels)."""
    if not gate_pass:
        return False, "spatial gate FAIL"
    if delta is None:
        return False, "no new labels: the candidate equals the champion's training set"
    if n_new is not None and n_new < min_new:
        return False, f"only {n_new} new labels (< {min_new}): too few to be worth a model swap"
    d, lo, _ = delta["qwk"]
    if d < 0 or lo <= -0.02:
        return False, f"new labels do not help on the paired test (ΔQWK {d:+.3f}, CI low {lo:+.3f})"
    return True, f"gate PASS and new labels help or are neutral (ΔQWK {d:+.3f}, CI low {lo:+.3f})"


# ---------------------------------------------------------------------------
# I/O steps
# ---------------------------------------------------------------------------
def log(msg):
    print(f"[retrain] {msg}", flush=True)


def run(cmd, env=None, check=True):
    log("$ " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})},
                       capture_output=True, text=True)
    out = p.stdout + p.stderr
    if check and p.returncode not in (0,):
        print(out)
        sys.exit(f"[retrain] step failed ({p.returncode}): {' '.join(cmd)}")
    return p.returncode, out


def load_old_cache():
    man = os.path.join(CACHE, "dataset_v2.csv")
    if not os.path.exists(man):
        return {"files": [], "feats": {}, "clip": np.zeros((0, 512)), "road_prob": []}, None
    df = pd.read_csv(man)
    F = np.load(os.path.join(CACHE, "feats_v2_small.npz"))
    C = np.load(os.path.join(CACHE, "clip_v2.npz"))
    return ({"files": list(df["image_filename"]), "feats": {k: F[k] for k in DINO_KEYS},
             "clip": C["clip"], "road_prob": df["is_road_prob"].values}, df)


def load_frame_feats():
    if not os.path.exists(FRAME_FEATS):
        return None
    z = np.load(FRAME_FEATS, allow_pickle=True)
    keys = list(z["keys"])
    if keys[:2] != ["cls", "patch"] or z["feats"].shape[1] != 2 * DIM:
        log(f"frame_feats_v2.npz has keys {keys}; not reusable")
        return None
    f = z["feats"].astype(np.float32)
    return {"ids": z["ids"], "cls": f[:, :DIM], "patch": f[:, DIM:]}


def db_frame_info(filenames):
    """{filename: (frame id, frame_quality.road_prob or None)} from Postgres."""
    try:
        import psycopg2
        url = os.environ.get("DATABASE_URL")
        if not url:
            for line in open(os.path.join(ROOT, ".env")):
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
        with psycopg2.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT id, image_url, analysis_metadata->'frame_quality'->>'road_prob' "
                        "FROM street_view_images WHERE image_url = ANY(%s)",
                        (["images/" + f for f in filenames],))
            return {u.split("/", 1)[1]: (i, None if p is None else float(p)) for i, u, p in cur.fetchall()}
    except Exception as exc:  # DB down: everything falls back to extraction
        log(f"WARNING: DB lookup failed ({exc}); new frames will be extracted")
        return {}


def check_frame_feats(ff, old, old_df, info):
    """Do frame_feats rows reproduce the cached cls/patch on frames in both?"""
    if ff is None or old_df is None:
        return ff
    pos = {int(i): j for j, i in enumerate(ff["ids"])}
    rows = [(i, pos[info[f][0]]) for i, f in enumerate(old["files"])
            if f in info and info[f][0] in pos][:200]
    if not rows:
        return ff
    a = np.stack([np.r_[old["feats"]["cls"][i], old["feats"]["patch"][i]] for i, _ in rows])
    b = np.stack([np.r_[ff["cls"][j], ff["patch"][j]] for _, j in rows])
    rel = float(np.median(np.linalg.norm(a - b, axis=1) / np.linalg.norm(a, axis=1)))
    log(f"frame_feats_v2.npz vs cache on {len(rows)} shared frames: median rel. diff {rel:.4f}")
    if rel > FRAME_FEATS_MAX_REL_DIFF:
        log("  -> does not match the training features (different preprocessing?); not reused")
        return None
    return ff


def extract(paths):
    import extract_features_v2 as E
    d = E.extract_dinov2(paths, E.BACKBONES["small"])
    emb, p = E.extract_clip(paths)
    return d, emb, p


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", help="use this labels CSV instead of exporting from the DB")
    ap.add_argument("--min-new", type=int, default=50)
    ap.add_argument("--force", action="store_true", help="continue with fewer than --min-new new labels")
    ap.add_argument("--no-extract", action="store_true")
    ap.add_argument("--run-dir")
    args = ap.parse_args(argv)

    import rqi_scale
    import spatial_cv as S
    from save_model_v2 import DROP_RQI5, ROAD_PROB_MIN

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    rd = args.run_dir or os.path.join(CACHE, "retrain", stamp)
    os.makedirs(rd, exist_ok=True)
    log(f"run dir {os.path.relpath(rd, ROOT)}; canonical scale direction: {rqi_scale.SCALE.direction} "
        f"(ML stays in severity: 1 = best)")

    # 1. export
    labels_csv = os.path.join(rd, "labels.csv")
    if args.labels:
        shutil.copyfile(args.labels, labels_csv)
    else:
        run(["bash", "ml/export_labels.sh"], env={"OUT": labels_csv, "PY": PY})
    labels = pd.read_csv(labels_csv)
    lv = labels["manual_rqi"].dropna()
    if len(lv) and (lv.min() < rqi_scale.MIN_LEVEL or lv.max() > rqi_scale.MAX_LEVEL):
        sys.exit(f"[retrain] labels outside {rqi_scale.LEVELS}: wrong scale orientation?")

    # 2. features
    import extract_features_v2 as E
    man = build_manifest(labels, lambda f: E.find_image(f) is not None)
    old, old_df = load_old_cache()
    if old_df is not None:
        ok, rho, n_ov = orientation_check(old_df, man)
        if not ok:
            sys.exit(f"[retrain] exported labels disagree with the cache on {n_ov} shared frames "
                     f"(Spearman {rho:+.2f}). Scale orientation mismatch? Check that "
                     "shared/rqi_scale.json matches the DB (ml/rqi_scale.py --sql) before retraining.")
    diff = diff_labels(old_df if old_df is not None else man.iloc[:0], man)
    log(f"labels: {len(labels)} rows, {len(man)} with an image; new {len(diff['new'])}, "
        f"changed {len(diff['changed'])}, removed {len(diff['removed'])}")
    if len(diff["new"]) < args.min_new and not args.force:
        log(f"only {len(diff['new'])} new labels (< --min-new {args.min_new}); nothing to do. "
            "Use --force to retrain anyway.")
        return 0
    need = [f for f in man["image_filename"] if f not in set(old["files"])]
    info = db_frame_info(list(man["image_filename"]))
    man["svi_id"] = [info.get(f, (s, None))[0] if pd.isna(s) else s
                     for f, s in zip(man["image_filename"], man["svi_id"])]
    ff = check_frame_feats(load_frame_feats(), old, old_df, info) if need else None
    rpd = {i: p for i, p in info.values() if p is not None}
    feats, clip, rp, src, todo = assemble_features(man, old, ff, rpd)
    if todo:
        if args.no_extract:
            sys.exit(f"[retrain] {len(todo)} frames need feature extraction (--no-extract given)")
        log(f"extracting DINOv2 + CLIP for {len(todo)} frames ...")
        d, emb, p = extract([E.find_image(man["image_filename"][r]) for r in todo])
        for k in DINO_KEYS:
            feats[k][todo] = d[k]
        clip[todo], rp[todo] = emb, p
    counts = pd.Series(src).value_counts().to_dict()
    log(f"feature sources: {counts}")
    man["is_road_prob"] = rp
    man.drop(columns=["svi_id"]).to_csv(os.path.join(rd, "dataset_v2.csv"), index=False)
    np.savez_compressed(os.path.join(rd, "feats_v2_small.npz"), **feats)
    np.savez_compressed(os.path.join(rd, "clip_v2.npz"), clip=clip, road_prob=rp)
    link = os.path.join(rd, "rqi_model.joblib")
    if not os.path.lexists(link):
        os.symlink(CHAMPION, link)

    # 3. coords
    coords = os.path.join(rd, "image_coords.csv")
    run([PY, "ml/build_coords.py", "--manifest", os.path.join(rd, "dataset_v2.csv"),
         "--labels", labels_csv, "--out", coords])
    env = {"RQI_ML_CACHE": rd, "RQI_ML_COORDS": coords}

    # 4. fit + 5. gate
    _, fit_out = run([PY, "ml/save_model_v2.py", "--out", "rqi_model_candidate.joblib"], env=env)
    cand = os.path.join(rd, "rqi_model_candidate.joblib")
    code, gate_out = run([PY, "ml/evaluate_artifact.py", cand], env=env, check=False)
    if code == 2:
        print(gate_out)
        sys.exit("[retrain] gate errored")
    gate_pass = code == 0

    # 6. reports (in-process, same filters as save_model_v2)
    import joblib
    from sklearn.base import clone
    S.COORDS = coords
    champ = joblib.load(CHAMPION)
    keys = champ["feature_recipe"]["keys"]
    X_all = np.hstack([feats[k] for k in keys])
    keep = (rp >= ROAD_PROB_MIN) & np.isfinite(X_all).all(1)
    if DROP_RQI5:
        keep &= man["rqi"].values != 5
    X, d = X_all[keep], man[keep].reset_index(drop=True)
    y, yc = d["manual_rqi"].values.astype(float), d["rqi"].values.astype(int)
    c = S.load_coords(d["image_filename"])
    groups = S.grid_cells(c["lat"].values, c["lon"].values)
    area = c["area"].values
    head = champ["pipeline"].steps[-1][1]
    make = lambda: clone(head)  # noqa: E731
    is_new = d["image_filename"].isin(diff["new"]).values
    rep = {"n_train": int(len(d)), "n_new_in_train": int(is_new.sum())}

    res_all = masked_nested_cv(X, y, yc, groups, make, np.ones(len(y), bool))
    rep["candidate_cv"] = S.ordinal_metrics(yc, res_all["pred"], res_all["oof"])
    delta = None
    if is_new.any():
        res_old = masked_nested_cv(X, y, yc, groups, make, ~is_new)
        delta = S.paired_bootstrap_delta(yc, res_old, res_all, groups)
        rep["paired_old_vs_all"] = delta
        ch = champ["pipeline"].predict(X[is_new])
        chp = np.digitize(ch, champ["thresholds"]) + 1
        rep["new_labels_champion"] = S.ordinal_metrics(yc[is_new], chp, ch)
        rep["new_labels_candidate_oof"] = S.ordinal_metrics(
            yc[is_new], res_all["pred"][is_new], res_all["oof"][is_new])
    bp = area == BUDAPEST
    if bp.any():
        rep["budapest_candidate_oof"] = S.ordinal_metrics(yc[bp], res_all["pred"][bp], res_all["oof"][bp])
        if (~bp).sum() > 50:
            tr = ~bp
            inner = S.nested_spatial_cv(X[tr], y[tr], yc[tr], groups[tr], make, tune=False)
            th = S.tune_thresholds(yc[tr], inner["oof"])
            o = S._fit_predict(make, X[tr], y[tr], X[bp])
            rep["leave_budapest_out"] = S.ordinal_metrics(yc[bp], np.digitize(o, th) + 1, o)

    ok, why = verdict(gate_pass, delta, len(diff["new"]), args.min_new)
    shutil.copyfile(cand, CANDIDATE)
    write_summary(rd, stamp, diff, counts, gate_out, gate_pass, rep, ok, why, len(labels))
    return 0


def _fmt(m):
    if not m:
        return "-"
    return (f"n={m['n']} QWK {m['qwk']:.3f} MAE {m['mae']:.3f} exact {m['exact']:.3f} "
            f"bad-AUC {m['bad_auc']:.3f}")


def write_summary(rd, stamp, diff, counts, gate_out, gate_pass, rep, ok, why, n_labels):
    gate_lines = [ln for ln in gate_out.splitlines() if any(
        t in ln for t in ("QWK", "MAE  ", "bad AUC", "[PASS]", "[FAIL]", "PASS —", "FAIL —", "n="))
        and "measurably better" not in ln]  # that line compares recipes; same recipe -> always NO
    lines = [f"# Retrain {stamp}", "",
             f"- labels exported: {n_labels}; new {len(diff['new'])}, changed {len(diff['changed'])}, "
             f"removed {len(diff['removed'])}",
             f"- feature sources: {counts}",
             f"- trained on {rep['n_train']} frames ({rep['n_new_in_train']} new)", "",
             "## Spatial gate (ml/evaluate_artifact.py)", "", "```", *gate_lines, "```", "",
             "## Reports", "",
             f"- candidate spatial CV: {_fmt(rep.get('candidate_cv'))}"]
    if "paired_old_vs_all" in rep:
        dq = rep["paired_old_vs_all"]
        lines.append("- paired, same folds, old labels only -> all labels: " + ", ".join(
            f"Δ{k} {v[0]:+.3f} [{v[1]:+.3f}, {v[2]:+.3f}]" for k, v in dq.items()))
        lines.append(f"- new labels only, champion (never saw them): {_fmt(rep['new_labels_champion'])}")
        lines.append(f"- new labels only, candidate OOF: {_fmt(rep['new_labels_candidate_oof'])}")
    lines.append(f"- Budapest only (candidate OOF): {_fmt(rep.get('budapest_candidate_oof'))}")
    lines.append(f"- leave-Budapest-out: {_fmt(rep.get('leave_budapest_out'))}")
    lines += ["", "## Verdict", "", f"**{'PROMOTABLE' if ok else 'KEEP THE CHAMPION'}**: {why}", ""]
    rel = os.path.relpath(rd, ROOT)
    if ok:
        lines += ["Promote (human decision; keeps a dated backup):", "", "```bash",
                  f"cp ml/cache/rqi_model.joblib ml/cache/rqi_model.{stamp}.bak.joblib",
                  "cp ml/cache/rqi_model_candidate.joblib ml/cache/rqi_model.joblib",
                  "```", "",
                  "Then refresh the shared caches to the new training set "
                  "(`ml/extract_features_v2.py`, `ml/build_coords.py`), and set `GATE` in "
                  "`ml/evaluate_artifact.py` to the new champion's numbers above.", ""]
    lines += [f"Run dir: `{rel}`. Candidate: `ml/cache/rqi_model_candidate.joblib`.", ""]
    rep_json = {k: v for k, v in rep.items()}
    with open(os.path.join(rd, "summary.json"), "w") as f:
        json.dump({"verdict": ok, "why": why, "gate_pass": gate_pass, "diff_counts":
                   {k: len(v) for k, v in diff.items()}, "feature_sources": counts, **rep_json},
                  f, indent=1, default=float)
    text = "\n".join(lines)
    with open(os.path.join(rd, "summary.md"), "w") as f:
        f.write(text)
    print("\n" + text)


if __name__ == "__main__":
    sys.exit(main())
