# Imagery sources: Google Street View vs Mapillary

*Prototype status 2026-11-26 (T-71). Not legal advice: get a proper legal read
before growth or monetisation ([LANDSCAPE.md](LANDSCAPE.md) risks).*

## Why a second source

Every training and scored frame today is Google Street View. Google Maps Platform
terms restrict caching, exporting and deriving content from Street View imagery,
and may forbid ML on it ([LANDSCAPE.md](LANDSCAPE.md), *unverified*). Mapillary
images are licensed **CC BY-SA 4.0**: we may store them, run a model on them and
show them, with attribution and share-alike.

## Code (prototype, no token yet)

`backend/app/services/mapillary_client.py` exposes the same two calls the
collector makes on the Street View client. So `network_collector.run_plan`,
`DbFrameStore` and the resume log work unchanged:

| Step | Street View (`sv_client`) | Mapillary (`mapillary_client`) |
|---|---|---|
| Find | free Metadata API at the point | Graph API v4 `/images` in a ±15 m bbox; nearest **non-panorama** within 15 m whose camera faces along the road (≤ 45° off the bearing, either direction) |
| Fetch | Static API 600×400, pitch −20°, heading = road bearing | `thumb_1024_url`, cropped to 3:2 keeping the **bottom** (road) and resized to 600×400 |
| Id | `pano_id` | `mly:<image id>` in `pano_id` (no collision, same dedup) |
| Date | `date` (month) | `captured_at` → month |
| Budget | `data/quota/street_view.json`, `GOOGLE_SV_MONTHLY_CAP` | `data/quota/mapillary.json`, `MAPILLARY_MONTHLY_CAP` (20 000); an image is booked before download |
| Rate | `GOOGLE_SV_RATE_PER_S` (1/s) | `MAPILLARY_RATE_PER_S` (2/s), steady, one request at a time |
| Credential | `GOOGLE_MAPS_API_KEY` as a request parameter | `MAPILLARY_TOKEN` in the `Authorization` header only; never in a URL, log line or exception. The CDN thumbnail URL is signed and gets no token |
| Stop | HTTP 403/429, quota statuses → `StreetViewFatal` | HTTP 401/403/429 → the same `StreetViewFatal` |

Each Mapillary frame row carries `analysis_metadata.imagery`: `source`,
`copyright` (`© <user>, Mapillary, CC BY-SA 4.0`), `licence`, `licence_url`,
`mapillary_id` and `page_url`. Image files are named `mly_<id>_….jpg`. Tests use a
fixture JSON shaped after the API docs (`backend/tests/fixtures/`), not a
recorded response: no token yet. Re-check the field names on the first real call.

**Not wired yet:** a `--source mapillary` switch in `scripts/collect_network.py`
(it builds a `StreetViewClient` today), panoramas, and UI attribution.

## Licence duties (CC BY-SA 4.0)

- **Attribution wherever a Mapillary image or a frame derived from it is shown:**
  the creator, "Mapillary", the licence with a link, and an indication of changes.
  Our crop and resize count as changes. The point card must render
  `analysis_metadata.imagery.copyright`, link `page_url`, and say "cropped/resized".
- **Share-alike:** a database or image set we *derive* from these images (crops,
  labelled frames) must be shared under CC BY-SA if we distribute it.
  - Model scores published on the map are a separate question from re-serving the
    images. A dataset release (e.g. labelled frames) would have to be BY-SA.
  - Don't mix Street View frames into anything published as BY-SA.
- **Mapillary terms** apply on top of the licence: API terms, commercial-use
  section, rate limits. LANDSCAPE.md notes §12 was not read; read it before
  production use.
- **Personal data:** Mapillary blurs faces and plates, but not perfectly. Keep the
  public site's no-stored-image policy, or blur again, before serving any frame.

## External training data: StreetSurfaceVis (T-58)

[StreetSurfaceVis v1.0](https://zenodo.org/record/11449977) (SurfaceAI, HTW Berlin;
Kapp, Hoffmann, Weigmann, Mihaljević 2024): 9,122 Mapillary images from Germany
with surface type and OSM-style quality labels, **CC BY-SA 4.0**. We use it for
**model research only** (`ml/external_data.py`, Era 16 of
[MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md)):

- Local copy: `data/external/streetsurfacevis/` (the 256 px `s_256.zip` + label
  CSV), gitignored. **Never commit, re-serve or show these images**; features
  derived from them stay in the gitignored `ml/cache/`.
- **Attribution** if a model trained on it ever ships or a result is published:
  "StreetSurfaceVis (SurfaceAI, HTW Berlin), images © Mapillary contributors,
  CC BY-SA 4.0", with the Zenodo link. Mapillary's terms apply to the images.
- **Share-alike:** releasing the derived feature set or a labelled image set built
  from it would have to be BY-SA. Model weights and map scores are a grey zone:
  ask before shipping a model trained on it (owner decision, together with T-57).

## Coverage caveats

- Budapest density is unchecked; crowdsourced coverage is patchy, uneven in age
  (check `captured_at`), and biased toward routes enthusiasts drive. Expect gaps
  where Google has full coverage.
- Cameras vary: phones, dashcams, action cams; fisheye, wipers, bonnets, night shots.
  `ml/frame_quality.py` flags (dark, blur, non-road) matter more here.
- Direction: a frame facing back along the road is accepted (the road surface is
  the same); a 90° side view is not.

## Before any Mapillary score reaches the map

The RQI model was trained and validated **only on Street View frames** (600×400,
pitch −20°, Google's camera). Mapillary is a different domain, so:

1. Collect a few hundred Mapillary frames on roads that already have Street View
   labels. Label them blind in the label queue, tagged by source.
2. Run `ml/evaluate_artifact.py` on them as a separate test domain: spatially
   grouped and stratified by source. Don't report one pooled number. The
   promotion gate's thresholds (QWK ≥ 0.774, MAE ≤ 0.405, bad-AUC ≥ 0.934) apply
   to the Mapillary subset on its own.
3. If it fails, try a source-aware head (source as a feature, or retrain with both)
   under the same spatial gate. Never raise the gate for convenience.
4. Until it passes, keep Mapillary frames out of segment aggregation, e.g. by
   marking them unusable via `analysis_metadata`, as frame_quality does.
