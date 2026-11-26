# Labelling guide

How to make manual labels on `/training/:id/review`: **RQI scoring** (the
"Minőség" panel → `manual_rqi`, which the `ml/` pipeline trains on) and **damage
polygons** (the "Hibák jelölése" panel → YOLO training data). The web UI does not
train the RQI model; `ml/` does ([ml/README.md](../ml/README.md)).

## Scale

The scale and its rubric are defined once in
[shared/rqi_scale.json](../shared/rqi_scale.json) (this table is a copy of it;
rules: [shared/README.md](../shared/README.md)). Today **lower = better**; the
review screen's buttons and the keys `1`–`5` set the value.

| RQI | UI label | rubric |
|---|---|---|
| 1 | **Kiváló** | New or freshly resurfaced, no visible defects. |
| 2 | **Jó** | Light wear, small cracks, good patches; does not affect driving. |
| 3 | **Közepes** | Visible crack networks, heavy patching, small potholes. |
| 4 | **Rossz** | Deep potholes, broken-up or very rough surface. |
| 5 | **Nagyon rossz** | Barely drivable: continuous potholes, disintegrated surface. |

- **Bad road** = Közepes or worse (≥ 3); the map's "Rossz út valószínűsége" is
  the model's probability of that.
- **5 (Nagyon rossz) is on the scale but not trained:** it has only 14 labels,
  mostly junk, and training drops every 5. Until the owner decides otherwise,
  label even the worst real road **4**. Never use 5 for non-road or broken
  frames: skip those (see below).
- Half steps (1.5, 2.5, 3.5) are accepted but discouraged; pick the nearer level.

## What to label (this matters most)

- **Few images from many places.** Consecutive frames (~10 m apart) show nearly the
  same asphalt; prefer one frame every 100–200 m, from many different towns.
  **Budapest** is under-represented (and the model is weakest there) — cover every
  road class, including 1s. Why: [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md), era 6.
- **Boundary cases, especially class 2.** Most errors sit on the 1|2 and 2|3
  boundaries. Be consistent: a road with one small crack that is a 2 today must
  not be a 3 tomorrow.
- **Balanced:** plenty of good roads (1–2), not just bad ones.
- **Varied:** time of day/shadows, asphalt colour (new black vs. old grey), wet roads.

## A good training image

- The road surface is clearly visible in the bottom ~40% of the frame.
- Polygons: mark a small but deep pothole clearly; shallow unevenness belongs in
  the score, not in a polygon.
- Do not score non-road frames (lobbies, pavements, indoors).
