# Labelling guide

How to make manual labels on `/training/:id/review`: **RQI scoring** (the
"Minőség" panel → `manual_rqi`, which the `ml/` pipeline trains on) and **damage
polygons** (the "Hibák jelölése" panel → YOLO training data). The web UI does not
train the RQI model; `ml/` does ([ml/README.md](../ml/README.md)).

## Scale

The scale and its rubric are defined once in
[shared/rqi_scale.json](../shared/rqi_scale.json) (this table is a copy of it;
rules: [shared/README.md](../shared/README.md)). **Higher = better** (like a
school grade, since 2026-11-26); the review screen's buttons and the keys `1`–`5`
set the value.

**Rate only the surface visible in the frame** — not the speed limit, not the
road class. The same image must always get the same label (speed limits belong
in route scoring, not in the label). Each level has a driver's test:

| RQI | UI label | rubric | driver's test |
|---|---|---|---|
| 5 | **Kiváló** | New or recently resurfaced, uniform, no visible defects. | – |
| 4 | **Jó** | Minor wear, a few small cracks or good patches. | the ride is unaffected |
| 3 | **Közepes** | Clearly worn: crack networks, many patches, ravelling, small potholes. | noticeable, but you drive normally |
| 2 | **Rossz** | Significant damage: frequent potholes, crumbling or broken surface, rough patchwork. | you slow down or steer around defects |
| 1 | **Nagyon rossz** | Damage dominates the surface, or it isn't properly paved: deep potholes you can't avoid, large areas of missing asphalt, gravel/dirt road. | walking pace, or risk to the car |

- **Bad road** = Közepes or worse (≤ 3); the map's "Rossz út valószínűsége" is
  the model's probability of that.
- **Use 1 (Nagyon rossz) whenever the rubric fits** — including unpaved
  (dirt, gravel) roads. The model does not predict it yet (only 14 old labels,
  mostly junk, are dropped from training); new labels are what can change that.
  Never use 1 for non-road or broken frames: skip those (see below).
- Half steps (2.5, 3.5, 4.5) are accepted but discouraged; pick the nearer level.

## What to label (this matters most)

- **Few images from many places.** Consecutive frames (~10 m apart) show nearly the
  same asphalt; prefer one frame every 100–200 m, from many different towns.
  **Budapest** is under-represented (and the model is weakest there) — cover every
  road class, including Kiváló roads. Why: [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md), era 6.
- **Boundary cases, especially Jó.** Most errors sit on the Kiváló|Jó and
  Jó|Közepes boundaries. Be consistent: a road with one small crack that is Jó
  today must not be Közepes tomorrow.
- **Balanced:** plenty of good roads (Kiváló, Jó), not just bad ones.
- **Varied:** time of day/shadows, asphalt colour (new black vs. old grey), wet roads.

## A good training image

- The road surface is clearly visible in the bottom ~40% of the frame.
- Polygons: mark a small but deep pothole clearly; shallow unevenness belongs in
  the score, not in a polygon.
- Do not score non-road frames (lobbies, pavements, indoors).
