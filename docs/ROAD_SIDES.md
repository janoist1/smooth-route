# Road sides: quality per travel direction

*Status 2026-11-28 (T-111…T-114). Owner request: analyse both directions. A road is
sometimes better on one side, and the planner should use the side it drives on.*

## The problem

Today a two-way road gets **one** score from frames that look one way:

- **Collection.** The network collector points the camera along the OSM way's
  drawing direction (`network_collector.py`). The route collector points it along
  the planned route.
- **Matching.** Matching ignores direction: `map_matching` compares bearings
  modulo 180°, and `build_rows` pools all frames of a piece into one aggregate.

On wide roads this has two effects:
- The far lanes are small, or hidden by oncoming traffic.
- A side that is worse than the other is averaged away.

Dual carriageways (motorways, most divided trunk roads) are already fine. OSM maps
each carriageway as its own `oneway` way, so each gets its own segments.

## What the data says (2026-11-28)

**Segments with frames: 2,312.** Coverage by road type:

| Road type (OSM tags) | Seen from both camera directions | One camera direction only |
|---|---|---|
| one-way / motorway / roundabout | 274 | 1,097 (fine: one direction exists) |
| two-way, 1–2 lanes | 5 | 615 (117 km) |
| two-way, ≥ 3 lanes | 7 | 307 (58 km) |

**Which lanes a frame shows well depends on where the Google car drove, not on
where the camera points.** The pano sits in the car's own lanes, and those stay
close in both camera directions. So the *side* of a frame is the side of the
centreline its pano is on.

On the 315 two-way multi-lane segments:
- **Frames:** 3,976 in total. Panos sit right of the centreline (median 3.9 m), left of it (median 2.3 m), or within 1 m (1,182 frames, too close to call). The asymmetry hints at a slightly offset OSM centreline.
- **Segments:** 88 already have panos on both sides, 124 only on the right, 77 only on the left, and 26 only near the centre.

**Free probe for the missing side.** Street View metadata is free. For each of 25 sampled multi-lane segments, I queried 6 m left and right of the midpoint with a 10 m radius. 10 of the 25 returned two different panos on opposite sides, one per travel direction.

Some of those panos are old (2014, 2016), so filter by date.

## Method

Hungary drives on the right, so with respect to the OSM way's drawing direction:
**right side = forward lanes, left side = backward lanes.**

1. **Side of a frame.** Compute the signed lateral offset of the pano position from the stitched line at the snapped point. Do this only for two-way lines (not `oneway`, not a roundabout, not `highway=motorway`).
   - Do not trust the absolute sign alone, because the centreline is biased. Per stitched line, split the offsets into two groups when there is a clear gap: group means ≥ 2.5 m apart, each group with ≥ 2 frames. The more-right group is `fwd`.
   - With one group only, assign a side if |offset| ≥ 1.5 m; otherwise the frame is `unknown`.
   - The camera heading does not decide the side.
2. **Aggregate per side.** Use the same `aggregate_frames` over the `fwd` frames and over the `bwd` frames, in addition to today's pooled aggregate. Today's pooled aggregate stays the segment's main score.
   - Store `score_fwd/rqi_fwd/n_fwd/confidence_fwd` and the `_bwd` equivalents. They are null when a side has no frames.
   - A side counts as **reliable** with ≥ 3 frames and the normal confidence rule.
3. **Planner.** For each route sample, the travel direction against the segment's drawing direction picks `fwd` or `bwd`. Use that side's class when it is reliable, else the pooled class.
4. **Map.** One line, as today. When both sides are reliable and differ by ≥ 1 class, the segment card shows both sides, e.g. "→ irányban: Jó, ← irányban: Rossz". Drawing two offset lines at high zoom is a later step (T-114).

## Phases

| Ticket | What | Cost |
|---|---|---|
| **T-111** | Side per frame + per-side aggregates + migration + GraphQL fields + planner uses the side + segment card | no downloads |
| **T-112** | Fill the missing side on two-way roads with ≥ 3 lanes. Use free metadata at a laterally offset point; accept a pano that is on the other side and not older than the existing side by > 3 years; fetch 1 image per ~25 m along that side's travel direction | ~450 Street View images for today's 227 one-sided multi-lane segments |
| **T-113** | Occlusion flag: a vehicle covering much of the lower road area. Down-weight or skip the frame (frame-quality flag) | model work, no downloads |
| **T-114** | Map: two offset lines per side at zoom ≥ 16 when the sides differ | frontend |

Per-lane scores (not just per side) would need lane-level labels. Out of scope until
the per-side numbers prove useful.
