# Imagery sources: Google Street View vs open imagery

*Status 2026-11-27 (T-57, T-106, T-110). Not legal advice.*

**Short answer (T-110).** For now, Google is the only source that is both continuous
and uniform: one camera model, the same height, no dashboard in view. Open imagery
exists in Hungary but is uneven. On our own segments only about a quarter have a
usable recent open frame ([measured](#measured-coverage-on-our-segments-t-110)).

The long-term source is **our own standardized capture plus volunteer drivers**
([plan](#own-capture--community-the-target-t-110)). Official road-condition data
is published only as county totals; section-level data needs a request
([details](#official-road-condition-data-magyar-közút)).

## Why a second source

Every training and scored frame today is Google Street View. **Verified
2026-11-27** in the primary texts (global Maps Platform ToS §3.2.3, EEA ToS §3.3.2;
the EEA terms govern a Hungarian billing account): Google forbids bulk-downloading
and storing Street View images, using Maps content to train, test, validate or
fine-tune ML models, and creating content based on Maps content. Our pipeline does
all three. Storing pano IDs is allowed (EEA Service Specific Terms). Owner decision
(T-57): the project is a test for now and the Street View images will be deleted;
any growth needs an open source.

| Source | Licence | ML + published scores | Notes |
|---|---|---|---|
| Mapillary | CC BY-SA 4.0 | allowed by the licence; Mapillary's own terms page needs a login and was not read | API client below exists; **coverage still unmeasured** (the API needs a token, i.e. a free account) |
| Panoramax | per instance: Etalab 2.0, or CC BY-SA 4.0 + an explicit AI/derived-data permission | explicitly allowed (federation policy) | has a road-damage → road-segment workflow in its docs; **almost nothing in Hungary** (3/80 sampled segments) |
| KartaView | CC BY-SA 4.0 (credit "© Grab and KartaView Contributors") | allowed by the licence | maintained (app update Oct 2026); API 100/h anonymous, 1,000/h with a token; **frames on 41/80 segments, usable on ~16–21** |
| Apple Look Around | Apple terms | no general ML or derived-score licence found | live in Hungary since 2023 ([Apple](https://www.apple.com/gw/newsroom/2023/04/apple-brings-new-map-to-austria-croatia-czechia-hungary-poland-and-slovenia/)); not a reusable source |
| Budapest Közút panorama | theirs | needs their permission | professional 360° survey panoramas, faces and plates blurred, sections re-measured yearly. **Not public:** only Budapest Közút staff and contracted KAPU partners can open them ([site](https://panorama.budapestkozut.hu/); the site still says the imagery is from 2018). Access would need a research partnership. Data requests are possible ([procedure](https://www.budapestkozut.hu/informatikai-igazgatosag/nyilvantartas-es-adatszolgaltatas/nyilvantartas-adatszolgaltatas/)) |
| Own capture (phone) | ours | ours | GDPR applies to raw frames (faces, plates): lawful basis, blur, retention; publishing only segment scores is the low-risk part |

Research with links: board T-57 / T-106 / T-110 (Codex, 2026-11-27).

## Measured coverage on our segments (T-110)

**Method (2026-11-27).**
- **Sample:** 80 random road segments from the dev DB, seed 0.42: 40 in Budapest, 40 elsewhere. Road types motorway to unclassified, length ≥ 30 m; no service roads, no links.
- **What counts as a hit:** a frame within 20 m of the segment midpoint that faces along the road (≤ 45° either way, or a 360° image) and was taken in 2021 or later. Data came from the public Panoramax and KartaView APIs.
- **Visual check:** for each KartaView segment with a hit, I looked at the newest matching frame on a contact sheet. Other frames of the same segment were not checked, so these usable counts are a lower bound.

| Source | Budapest (40) | Elsewhere (40) | Recent + aligned | Usable road view |
|---|---|---|---|---|
| Panoramax | 2 | 1 | 2 | – |
| KartaView | 27 | 25 | 41 | **16** clear + 5 borderline |

The 20 frames rejected on visual inspection fail for these reasons:
- **Sky-heavy framing:** the phone points upward, so only a thin strip of road shows. Many 2026 frames come from one heavy contributor with this setup.
- **Light and focus:** night shots, glare, rain on the windscreen, motion blur.
- **Wrong viewpoint:** sidewalk, cycle-path or footbridge views.

Dashboards, wipers and windscreen suction mounts are in most frames. This confirms the owner's view: open imagery has volume, but not one camera standard.

## Official road-condition data (Magyar Közút)

Magyar Közút publishes **"Országos közutak burkolatállapot adatai (2025.12.31.)"** (175 KB XLS, posted 2026-07-11, [download page](https://internet.kozut.hu/download/orszagos-kozutak-burkolatallapot-adatai-2025-12-31/)). What it contains:
- **Measures:** four of them — rut depth, IRI (roughness, mm/m), visual surface condition and bearing capacity.
- **Granularity:** **county-level km and % totals** in five classes (Jó … Rossz), split into main and secondary network. **No section-level rows.**
- **Licence:** the older data-portal entry is labelled CC non-commercial ([opendata.gov.hu](https://opendata.gov.hu/dataset/2cd3742d-17e5-4f12-8a31-9e7e3fa13963)).

What it is good for:
- A sanity check of our score distribution per county.
- Not usable for calibrating the model per segment.

Getting section-level data:
- Section-level IRI and distress data (road number, chainage, date, method) would need a public-information request.
- A 2024 request got only averages ([kimittud.hu](https://kimittud.hu/request/utallapotok)), so ask for the section table explicitly.
- Budapest Közút also takes data requests, and waives fees for university work.

## Own capture + community: the target (T-110)

**Lesson from commercial systems:** standardize the *process* before buying hardware.
- Vialytics shoots a frame about every 4 m ([blog](https://www.vialytics.com/blog/behind-the-scenes-of-the-vialytics-ai-data-platform)).
- RoadBotics and Vaisala use phones in a fixed mount on planned routes ([RoadBotics](https://www.roadbotics.com/wp-content/uploads/2021/09/RoadBoticsCorporateBrochurev3-digital.pdf), [Vaisala](https://www.vaisala.com/sites/default/files/documents/WEA-GLO-GT-ProductSpotlight-Road-AI-v5.pdf)).
- Roadroid calibrates per vehicle, mount and speed ([manual](https://www.roadroid.com/common/References/Roadroid%20User%20Guide%20-%20Pro%20Version.pdf)).

| Rig | Cost (EUR, Nov 2026) | Note |
|---|---|---|
| Phone in a fixed windscreen mount | 30–60 for accessories | first choice; volunteers already own one |
| GPS dashcam (e.g. VIOFO A119 Mini 2) | ~116 | 1440p video + GPS; frames picked by distance afterwards |
| 360 camera (Insta360 X5 / GoPro MAX) | ~440 (+~93 for a GPS remote) / 250–400 | best views in the KartaView sample; buy only if a paired test shows a gain |
| Raspberry Pi + Camera Module 3 + GNSS | 120–200 (estimate) | full control, most build work |

**Capture protocol (draft).**
- Same mount height and pitch every time, with the road in the lower half. Match our Street View frames (pitch −20°, heading along the road) so the model's domain gap stays small.
- Daylight and a dry road only.
- One frame every ~10 m, triggered by distance, not by time.
- Record the mount metadata (height, pitch, phone model) with each run.

**Apps:** none of the ready apps fits fully, so a small capture mode of our own (web app or app) is likely.
- Open Camera has only timed capture.
- The Panoramax and Baba apps (AGPL) are unverified for distance triggering.
- The Mapillary app spaces frames about 3 m apart in town and 20 m above 50 km/h ([forum](https://forum.mapillary.com/t/new-smart-spacing/7318)).

**Accelerometer (same drive).** Phone-based roughness estimates track measured IRI fairly well; a 2024 study reports RMSE 0.60 and R² 0.79 ([Monash](https://research.monash.edu/en/publications/smartphone-based-iri-estimation-for-pavement-roughness-monitoring/)).
- It needs calibration per vehicle.
- Sampling is ~100 Hz with speed correction ([SmartRoadSense](https://www.mdpi.com/1424-8220/17/2/305)).
- The World Bank's RoadLab Pro is Apache-2.0 ([repo](https://github.com/WorldBank-Transport/RoadLab-Pro)).
- Keep *ride roughness* and the *visual RQI* as separate outputs at first, and compare them on repeated runs.

**Privacy (GDPR, Hungary).** Volunteer consent does not cover bystanders.
- NAIH judged one continuous dashcam use disproportionate (its 2020 opinion on fuel trucks; [NAIH](https://www.naih.hu/adatvedelmi-allasfoglalasok?download=68:fedelzeti-kamera-alkalmazhato-e-az-uzemanyag-szallitast-vegzo-gepjarmuvek-biztonsagossa-tetele-erdekeben)). A mapping run therefore needs:
  - its own lawful basis and balancing test;
  - transparency;
  - a retention rule.
- Blur faces and plates **before** durable storage, using SGBlur (MIT) or EgoBlur (Apache-2.0).
- Write volunteer terms that cover image rights, ML reuse, location privacy and deletion.

**Hosting.**
- **Panoramax OSM-FR:** accepts test uploads from anywhere.
- **Self-hosted Panoramax:** its enhanced CC BY-SA licence requires derived data, *including AI models and training sets*, to stay open ([policy](https://docs.panoramax.fr/federated-catalog/)).
- **Own object storage:** e.g. Hetzner, ~€0.0104/h including 1 TB. We then carry the privacy, takedown and backup duties ourselves.

**Community minimum.**
- Contributor side: resumable Wi-Fi upload, a mount checklist, instant quality feedback and credit for contributors.
- Map side: a gap/age map and "your km are on the map".
- Recruit a small recurring fleet before an open call.

**Phases (go/no-go).**
0. **Now, €0.**
   - Prototype stays on Google (T-57 owner decision).
   - Measure Mapillary (needs a free account).
   - Ask Magyar Közút for section-level IRI.
1. **Phone pilot** (owner's car, after the China trip).
   - A 20–50 km mixed loop, driven several times with two phones; camera + accelerometer; blind labels.
   - **Go:** ≥ 90 % usable frames, repeated runs rank the segments the same way, and the model passes the gate on this subset ([before any Mapillary score…](#before-any-mapillary-score-reaches-the-map) applies the same way).
2. **~5 recurring drivers for 8 weeks.**
   - Pick the host and document the privacy routine.
   - **Go:** drivers keep contributing.
3. **Open call.**

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
