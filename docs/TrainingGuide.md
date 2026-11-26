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

## Quick-rate weak spots

On the phone, open `/training/quick` and choose **Gyenge pontok**. This targets
the systematic errors found in [Era 16](MODEL_EXPERIMENTS.md#era-16--external-training-data-streetsurfacevis-and-the-budapest-errors-t-58-t-43-2026-11-26):
aged motorway asphalt with cracks, and inner-city road markings the model
confuses with damage. Keep using the same rubric above: score the visible
surface, regardless of the road class. The model guess remains hidden until
rating; skip and undo work as in the other modes. These labels count toward the
same 1000-label sprint as **Sprint**.

The default mix is 45% motorway/trunk frames predicted Kiváló (including ramps),
45% frames predicted Közepes in the coverage report's approximate inner V–IX box,
and 10% Budapest frames in cells with no label. All frames must be unlabelled,
usable and present locally. Shared 150 m thinning spreads picks across streets;
a stable shuffle hides the rule order. A dry rule yields its share to the others.
The queue ends when all enabled pools are exhausted; it never falls back to
unrelated or already-labelled frames.

Maintainers can tune `backend/config/weak_spots.json` (shares, scale keys,
road classes, bbox and thinning); restart the backend after editing. Details
and the read-only count command are in the
[queue API documentation](API_SURFACE.md#labelling-admin).
