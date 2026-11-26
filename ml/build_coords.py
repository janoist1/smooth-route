#!/usr/bin/env python3
"""
Attach a GPS coordinate to EVERY labelled training image -> ml/image_coords.csv

Why: honest (spatially grouped) cross-validation needs to know where each
image was taken. Neighbouring Street View frames (~10 m apart, same street)
are near-duplicates; if one lands in the train fold and its neighbour in the
test fold, the CV score is optimistic. See ml/spatial_cv.py.

Two filename schemes exist in ml/cache/dataset_v2.csv:
  1. ``00001_47.496700_19.069360_67.jpg``  -> seq_lat_lon_heading, parsed directly
  2. ``sv_{svi_id}_{uuid}.jpg``             -> coordinates live in the DB table
     ``street_view_images`` (row id = svi_id). Looked up, in order, in:
       a. ``ml/labels.csv`` latitude/longitude columns (ml/export_labels.sh
          joins them in, so every new label — review page or the quick-rate
          screen — carries its coordinate);
       b. the older DB export ``ml/missing_labelled_mapped.csv`` (produced
          when images were recovered, see ml/recover_missing_images.py);
       c. Postgres (``docker compose up -d db``, :5433) for anything still
          missing — always with ``--from-db``, otherwise as an automatic
          fallback when the DB is reachable.

The output is committed (small, ~2k rows) so the promotion gate does not depend
on the git-ignored DB export. Re-run only when the labelled set changes.

Columns: image_filename, lat, lon, seq, coord_source, area
  - seq   : capture order along the collection track (filename index / svi_id)
  - area  : which of the collection areas the image belongs to (see AREAS)

Usage:
  .venv/bin/python ml/build_coords.py             # labels.csv / CSV export, DB fallback
  .venv/bin/python ml/build_coords.py --from-db   # sv_* coordinates from Postgres
"""
import argparse
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ml", "cache")
MANIFEST = os.path.join(CACHE, "dataset_v2.csv")
LABELS = os.path.join(ROOT, "ml", "labels.csv")
SVI_EXPORT = os.path.join(ROOT, "ml", "missing_labelled_mapped.csv")
OUT = os.path.join(ROOT, "ml", "image_coords.csv")
DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5433/smooth_route")

NAMED = re.compile(r"^(\d+)_(-?\d+\.\d+)_(-?\d+\.\d+)_")
SVI = re.compile(r"^sv_(\d+)_")

# The labelled set was collected in four separate areas (DBSCAN, eps=2 km, gives
# exactly these four clusters). Centroids are the cluster means; an image is
# assigned to the nearest centroid if it is within MAX_AREA_KM, else "other".
AREAS = {
    "budapest": (47.4981, 19.0713),        # Budapest VII-VIII. ker. (Keleti)
    "torokbalint": (47.4330, 18.9002),     # Törökbálint-Budaörs (agglomeráció)
    "szekesfehervar": (47.1505, 18.4101),  # Székesfehérvár déli része
    "tapolca": (46.8681, 17.3897),         # Tapolca környéke (Balaton-felvidék)
}
MAX_AREA_KM = 15.0


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    h = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(h))


def assign_area(lat, lon):
    names = list(AREAS)
    d = np.stack([haversine_km(lat, lon, *AREAS[n]) for n in names], axis=1)
    idx = d.argmin(1)
    out = np.array([names[i] for i in idx], dtype=object)
    out[d.min(1) > MAX_AREA_KM] = "other"
    return out


def svi_coords_from_csv(labels_path=LABELS, export_path=SVI_EXPORT):
    """svi_id -> (lat, lon) from the CSV exports (labels.csv wins)."""
    out = {}
    for path in (export_path, labels_path):  # later file overrides earlier
        if not path or not os.path.exists(path):
            continue
        df = pd.read_csv(path)
        if not {"latitude", "longitude"} <= set(df.columns):
            continue
        if "svi_id" not in df.columns:
            df["svi_id"] = df["image_filename"].str.extract(SVI.pattern, expand=False)
        df = df.dropna(subset=["svi_id", "latitude", "longitude"])
        for r in df.itertuples():
            out[int(r.svi_id)] = (float(r.latitude), float(r.longitude))
    return out


def svi_coords_from_db(ids):
    import psycopg2

    with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, latitude, longitude FROM street_view_images "
                    "WHERE id = ANY(%s)", (list(ids),))
        return {int(i): (float(a), float(b)) for i, a, b in cur.fetchall()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-db", action="store_true",
                    help="read sv_* coordinates from Postgres instead of the CSV exports")
    ap.add_argument("--manifest", default=MANIFEST, help=argparse.SUPPRESS)
    ap.add_argument("--labels", default=LABELS, help=argparse.SUPPRESS)
    ap.add_argument("--out", default=OUT, help=argparse.SUPPRESS)
    args = ap.parse_args()

    files = pd.read_csv(args.manifest)["image_filename"].tolist()
    rows, need_svi = [], {}
    for f in files:
        m = NAMED.match(f)
        if m:
            rows.append((f, float(m.group(2)), float(m.group(3)),
                         int(m.group(1)), "filename"))
            continue
        m = SVI.match(f)
        if m:
            need_svi[f] = int(m.group(1))
            continue
        rows.append((f, np.nan, np.nan, -1, "missing"))

    if need_svi:
        ids = set(need_svi.values())
        if args.from_db:
            lookup = svi_coords_from_db(ids)
        else:
            lookup = svi_coords_from_csv(args.labels)
            missing = ids - set(lookup)
            if missing:
                try:
                    lookup.update(svi_coords_from_db(missing))
                    print(f"{len(missing)} sv_* coordinates read from Postgres")
                except Exception as exc:  # DB down: reported as missing below
                    print(f"WARNING: {len(missing)} sv_* frames have no coordinate "
                          f"in the CSV exports and the DB is unreachable ({exc}). "
                          f"Re-run bash ml/export_labels.sh or use --from-db.")
        for f, sid in need_svi.items():
            lat, lon = lookup.get(sid, (np.nan, np.nan))
            src = "svi_db" if np.isfinite(lat) else "missing"
            rows.append((f, lat, lon, sid, src))

    out = pd.DataFrame(rows, columns=["image_filename", "lat", "lon", "seq",
                                      "coord_source"])
    out = out.set_index("image_filename").loc[files].reset_index()
    ok = out["lat"].notna()
    out["area"] = "unknown"
    out.loc[ok, "area"] = assign_area(out.loc[ok, "lat"].values,
                                      out.loc[ok, "lon"].values)
    out["lat"] = out["lat"].round(7)
    out["lon"] = out["lon"].round(7)
    out.to_csv(args.out, index=False)

    print(f"{len(out)} images -> {os.path.relpath(args.out, ROOT)}")
    print(out["coord_source"].value_counts().to_string())
    print(out["area"].value_counts().to_string())
    if (~ok).any():
        print(f"ERROR: {int((~ok).sum())} images have no coordinate")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
