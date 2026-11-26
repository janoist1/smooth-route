# Labelling guide

How to make manual labels on `/training/:id/review`: **RQI scoring** (the
"Minőség" panel → `manual_rqi`, which the `ml/` pipeline trains on) and **damage
polygons** (the "Hibák jelölése" panel → YOLO training data). The web UI does not
train the RQI model; `ml/` does ([ml/README.md](../ml/README.md)).

## Scale (lower = better)

| RQI | meaning |
|---|---|
| 1 | excellent — new or freshly resurfaced, no visible defects |
| 2 | good — light wear, small cracks, good patches; does not affect driving |
| 3 | fair — visible crack networks, patching, small potholes |
| 4 | poor — deep potholes, broken-up or very rough surface |

Do not use 5: too few examples; training drops it.

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
