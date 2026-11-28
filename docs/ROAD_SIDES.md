# Road sides: quality per travel direction

*Status 2026-11-28 (T-111…T-114). The owner asked to analyse both directions: a road
is sometimes better on one side, and the planner should use the side it drives on.
**Result: per-side quality from Street View is parked.** Google does not tell us
which way its car drove (see below). The parts that work today are planned as
T-112 and T-113.*

## The problem

Today a two-way road gets **one** score from frames that look one way:

- **Collection.** The network collector points the camera along the OSM way's drawing
  direction (`network_collector.py`). The route collector points it along the
  planned route.
- **Matching.** It ignores direction: `map_matching` compares bearings modulo 180°,
  and `build_rows` pools all frames of a piece.

On wide roads this has two effects:
- The far lanes are small, or hidden by oncoming traffic.
- A side that is worse than the other is averaged away.

Dual carriageways (motorways, most divided trunk roads) are already fine. OSM maps
each carriageway as its own `oneway` way, so each gets its own segments.

| Segments with frames (2,312), by OSM tags | Seen from both camera directions | One camera direction only |
|---|---|---|
| one-way / motorway / roundabout | 274 | 1,097 (fine: one direction exists) |
| two-way, 1–2 lanes | 5 | 615 (117 km) |
| two-way, ≥ 3 lanes | 7 | 307 (58 km) |

## Why per-side quality is parked

Which lanes a frame shows well depends on where the Google car drove, not on where
the camera points. So a frame's side would have to come from the travel direction
of the car. **The Street View Static API does not give that direction.** Its metadata
has only the location, pano id and date, so the pano's position was the only clue.

What we tried (T-111, branch `codex/t111-road-sides`, commit 474e9f7, local only).
The plumbing worked and passed every gate: per-side columns, GraphQL `sides`, the
planner picking the driven side, and the segment card. The side signal did not:

1. **Pano position against the OSM centreline.** Within *one* drive the lateral offset wanders 2–5 m along the road:
   - Rákóczi út: one drive went from +6 m to −2 m.
   - Haraszti út: one drive went from −3 m to +2 m.
   - Váci út: one drive spread over +2 to +13 m.
2. **Rules tried, both failed on real data:**
   - "Split at the largest lateral gap": a continuous spread always has a gap.
   - "Frames clearly on both sides of the line, overlapping along the road": still split the Haraszti út drive, because panos from older runs (2019, 2022) are mixed into the same stretch.
3. An earlier count claimed that 88 of 315 multi-lane segments "already have both sides". It was wrong: it mixed in legacy frames whose stored position is an interpolated route point, not a pano.

The dev DB was restored to Alembic 0010 and rebuilt with the current engine, with a
backup in `data/backups/`. Nothing of T-111 is merged.

**What would unblock it:**
- **Own capture** (docs/IMAGERY_SOURCES.md): the phone's GPS course gives the travel direction of every frame, so the side is known exactly. The parked plumbing can be reused.
- Or **image-based side detection**: in a forward-looking frame, the road's centre marking left of the image centre means the car is in the forward lanes. This is ML work and needs labels.

## What works with Street View today

| Ticket | What | Cost |
|---|---|---|
| **T-112** | **More views on two-way roads with ≥ 3 lanes**, pooled into the normal score. Free metadata 6 m left and right of the centreline often returns a second pano from another drive: 10 of 25 probed segments. Those views show the far lanes closer. The collector's near-existing dedupe must allow it, and very old panos must be filtered out | ~450 Street View images for ~315 segments |
| **T-113** | **Occlusion flag:** a vehicle covering much of the lower road area. Down-weight or skip the frame (frame-quality flag) | model work, no downloads |
| T-111 / T-114 | Per-side scores + two offset lines on the map | parked until a direction-aware source exists |
