# Landscape — similar initiatives (Hungary + abroad)

Researched 2026-11-26 (web, text only). **(unverified)** = only secondary sources or
vendor marketing were found. Licence column is the question that matters for us:
*can we reuse their data or code?*

## 1. Comparison

### Hungary

| Initiative | What / data source | Coverage | Model / licence | Usable by us? |
|---|---|---|---|---|
| [Járókelő.hu](https://jarokelo.hu) | Civic issue reporting (photo + pin), volunteers forward to the authority. ~200k reports since 2012, >11k potholes ([Telex 2024](https://telex.hu/belfold/2024/12/11/jarokelo-problemamegoldo-szazezer-zebra-katyu-bokor), [WLB 2026](https://welovebudapest.com/cikk/2026/08/11/jarokelo-200-ezredik-bejelentese-budapest/)) | Budapest + other towns | Non-profit association; platform code [GPL-3.0](https://github.com/jarokelo/jarokelo). There's an API (third-party clients exist); terms for the data not found **(unverified)** | Partner, not a data source: discrete point reports, not segment quality. Ran a [Mapillary partnership in 2017](https://blog.mapillary.com/community/2017/04/13/uniting-against-potholes-jarokelo-mapillary.html) |
| [Munipolis](https://www.autonavigator.hu/autosvilag_hirei/katyubejelentes-uj-szinten-applikacio-foto-gps-kesz) | Municipal app: citizens send pothole photo + GPS to their council | ~200 Hungarian settlements | Commercial SaaS for councils | No open data |
| Budapest Közút | Operator's own defect inventory: 26k potholes logged over winter 2025/26, 1,966 reported in one day ([Telex](https://telex.hu/belfold/2026/02/18/katyu-budapest-kozut-javitas)); online claims form | Budapest (city roads) | Public body; no open per-segment condition data found | Ask for data (FOI or partnership). Their pothole counts are useful context |
| Magyar Közút annual condition survey | Measured surface condition, roughness (unevenness), rutting, bearing capacity; 5 classes *jó…rossz*; published since 2013, Excel tables per year ([Telex 2019 map](https://telex.hu/g7/kozelet/2019/06/10/ezen-a-terkepen-megnezheted-hol-a-legrosszabbak-az-utak-az-orszagban), [talk-hu](https://lists.openstreetmap.org/pipermail/talk-hu/2020-February/014045.html)) | ~32k km national network, **not** local streets | Public statistics; current download URL and licence not confirmed **(unverified)**. NAP portal (`napportal.kozut.hu`) needs registration and has no ODbL grant ([talk-hu 2019](https://lists.openstreetmap.org/pipermail/talk-hu/2019-November/013631.html)) | **Best ground truth available** for national roads: measured roughness per section → validate our RQI on main roads |
| Útinform (Magyar Közút) | Traffic events, roadworks, closures; reporting form | National | Public | Not road quality |
| HUN-REN SZTAKI + D3 Seeron ([ERCIM 2024](https://ercim-news.ercim.eu/en138/r-i/d3---an-ai-based-solution-to-road-defect-detection)) | Camera + LiDAR pothole/speed-bump/manhole detection, on-vehicle, real time. 6-month ESA Spark project, ended 03/2024 | Prototype | Research; no code or data released | Contact for collaboration only |
| BME (Horváth V. Gy., Barsi Á.), [Geodézia és Kartográfia 2025/4](https://ojs.elte.hu/geodeziaeskartografia/article/download/12111/10127/31294) | CNN road-defect recognition from smartphone images | Research | Academic paper | Possible academic partner and labelled-data exchange |

No Hungarian product found that rates **whole-network** surface quality from imagery or
offers "smoothest route" routing. Closest: Magyar Közút's survey (national roads only,
yearly, table form) and civic point reports.

### Commercial, abroad

| Product | Data source | Coverage | Business model | Usable? |
|---|---|---|---|---|
| [vialytics](https://www.vialytics.de/en/) (DE) | Phone on a council vehicle windscreen, photo every ~4 m, AI defects + PCI/PASER per segment | 500–1,000+ municipalities, 7 countries (figures vary) | B2G subscription priced by network km | No. Their **method** (dedicated phone, fixed interval, segment index) is the template for our accelerometer/camera drives |
| [Michelin Mobility Intelligence — Better Roads](https://mobilityintelligence.michelin.com/us/practical-applications-of-artificial-intelligence-and-machine-learning-for-better-road-maintenance) (ex-RoadBotics, [acquired 2022](https://cs.cmu.edu/news/2022/michelin-acquires-roadbotics)) | Smartphone video, deep learning, rating every ~3 m, colour-coded map | 250+ governments, mostly US | B2G | No |
| [Vaisala Xweather RoadAI](https://www.vaisala.com/products/road-asset-management) (FI) | Phone video, 11 defect types, PCI per section | Nordics, UK pilots | B2G | No |
| [Blyncsy / Bentley](https://www.bentley.com/software/blyncsy/) (US) | **Crowdsourced dashcams** (Nexar, >1M vehicles), PASER scores per segment, no field drives | US DOTs | B2G, list price ~$8/mile **(vendor page)** | No. Shows the "use imagery someone else already collected" model sells — the same bet we make with Street View |
| [NIRA Dynamics RSI](https://niradynamics.se/road-surface-information/) (SE, VW/CARIAD) | Wheel-speed and chassis signals from normal cars → roughness, friction, potholes; sold via HERE and Wejo "Road Health" | Several EU markets incl. Sweden's Trafikverket procurement | B2B/B2G data | No (closed). Proves car-fleet roughness ≈ the objective signal we want from phones |
| [Mercedes Car-to-X](https://autovista24.autovistagroup.com/news/daimler-uses-car-to-x-technology-for-pothole-detection/) | Suspension events → cloud → warnings to other Mercedes cars | Mercedes from 2016 onward | Customer feature | No |
| [Waze for Cities](https://waymo.com/blog/2026/04/partnering-with-waze-to-help-cities-patch-their-potholes/) | User pothole hazard reports; since 04/2026 also Waymo robotaxi detections (5 US metros) | Global (user reports); Waymo part US only | Free for public agencies | Only via a city partner; point hazards, short-lived |
| [Roadroid](https://thefonecast.com/News/monitoring-road-quality-with-a-standard-smartphone-and-the-roadroid-app) (SE), [RoadLab Pro](https://apps.apple.com/gt/app/roadlabpro/id1125333158) (World Bank), IRITracker, MIT Carbin | Phone accelerometer + GPS → estimated IRI. Roadroid claims ~80% of laser accuracy (vendor); RoadLab Pro is free | Global apps | Roadroid commercial; RoadLab Pro free (open-source claim **unverified**) | Method reference for our accelerometer phase (eIRI per 100 m, speed normalisation, phone mount) |
| SureRoad, Pada, Potholed (apps) | Pothole/roughness-aware car routing **(vendor claims, unverified)** | US/UK, small | Consumer apps | Direct "smoothest route" competitors abroad; none covers Hungary |

### Open / community / academic

| Item | What | Licence | Usable? |
|---|---|---|---|
| OSM [`smoothness`](https://wiki.openstreetmap.org/wiki/Key:smoothness) + `surface` | 8 levels `excellent…impassable`, photo [gallery](https://wiki.openstreetmap.org/wiki/Key:smoothness/Gallery). **Hungary: 88.8k of 1.10M highway ways (~8%) tagged** ([taginfo, 2026-11-24](https://taginfo.geofabrik.de/europe:hungary/keys/smoothness)); top values good 24k, excellent 22k, intermediate 15k, bad 15k | ODbL | Yes as an input signal (attribution; derived DB = ODbL share-alike if we publish it as a database) |
| [StreetComplete](https://wiki.openstreetmap.org/wiki/StreetComplete/Quests) | Android app with a smoothness quest built on the wiki gallery | GPL-3.0 | Volunteers who already rate smoothness; a channel to feed our results back as *survey*, never as AI auto-edits |
| [SurfaceAI](https://surfaceai.github.io/surfaceai/index_en) (HTW Berlin, mFUND) + [StreetSurfaceVis](https://zenodo.org/record/11449977) | **Closest academic twin**: Mapillary images → surface type + quality (OSM-aligned 5 levels) → aggregated onto OSM ways. 9,122 labelled images, mostly Germany; inter-rater α 0.74 for quality | Dataset CC BY-SA 4.0 (Mapillary images); [code](https://github.com/SurfaceAI/road_network_classification) CC BY-SA 4.0 | **Yes**: extra training/validation data and method comparison. Share-alike applies to derived datasets |
| [RDD2022](https://arxiv.org/abs/2209.08538) / CRDDC, ORDDC'2024 ([sekilab](https://github.com/sekilab/RoadDamageDetector)) | 47k images, 6 countries (incl. Czechia, Norway), 4 damage classes (cracks, potholes) | Code MIT; dataset CC BY-SA 4.0 per mirrors **(unverified on primary page)** | Yes for the YOLO defect-polygon side, not for RQI grades |
| [Mapillary](https://help.mapillary.com/hc/en-us/articles/115001770409) | Crowdsourced street imagery + free detection API | Images CC BY-SA; commercial use has extra terms (ToS §12, not read) | Alternative/complementary imagery that we *may* store and re-serve, unlike Street View. Budapest coverage density not checked |
| Street View pavement papers: [Ma et al. BMVC 2017](https://www3.cs.stonybrook.edu/~cvl/pavement.html) (700k GSV images × NYC ratings), [Majidifar et al. 2020](https://arxiv.org/pdf/2004.13314) (GSV → PCI) | Same idea as ours: Street View frames ↔ official ratings | Fetch code MIT; images not redistributable | Method validation: matching GSV to official ratings is how they got labels at scale |
| SmartRoadSense (EU), BikeVibes (cycling) | Open accelerometer crowdsourcing of roughness; SmartRoadSense seems abandoned ([OSM diary](https://www.openstreetmap.org/user/chris_debian/diary/401214)) **(unverified)** | Open source (per project pages) | Code reference for the phone-sensor phase |

### Routing on smoothness/surface

| Engine / app | What it supports | Licence |
|---|---|---|
| [GraphHopper](https://github.com/graphhopper/graphhopper) | `smoothness` and `surface` encoded values usable in custom models (priority/speed per value) | Apache-2.0 |
| [openrouteservice](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/routing-options) | Wheelchair/cycling `restrictions.smoothness_type` (default `good`), `surface_type`, kerb height | GPL-3.0 |
| [Valhalla](https://docs.stadiamaps.com/guides/getting-the-best-routes-with-valhalla-turn-by-turn-directions-apis/) | Bicycle `avoid_bad_surfaces` 0…1, `bicycle_type` | MIT |
| [BRouter](https://brouter.de/brouter/costfunctions.html) | Free-form cost profiles; smoothness multiplies surface quality (×1.1 excellent … ×0.5 very_bad) | MIT |
| OSRM | Car/bike Lua profiles can read surface/smoothness (speed penalties); default car profile does little | BSD-2 |
| Komoot, Strava | Surface shown per route; weighting not documented | Proprietary |

Car "smoothest route" is the gap: engines support it, but nobody feeds them good
**car-road** quality data in Hungary (OSM smoothness is mostly on tracks/paths and 8% overall).

## 2. What this means for Kátyúőr

**Where we're differentiated**
- *Network-wide, no driving, no fleet:* B2G vendors need a vehicle to drive every road; car
  fleets (NIRA, Mercedes) are closed. We rate any street with Street View coverage.
- *Hungarian, public, free, for drivers:* nobody in Hungary publishes a per-segment quality
  map of local streets or offers smoothest-route choice. Járókelő/Munipolis are point
  reports to authorities; Magyar Közút covers national roads only, yearly, as tables.
- *Grade, not just defects:* most open work (RDD) detects damage boxes; we output an
  OSM-compatible 5-level grade per segment, like SurfaceAI (which is Germany-only, bike-focused).

**Borrow**
1. **Validate on Magyar Közút survey data** (national roads): request the yearly section-level
   roughness/condition tables; compare our 200 m segment RQI → honest external metric.
2. **StreetSurfaceVis** (CC BY-SA) as an out-of-domain test set and maybe extra training
   data (map its 5 quality levels to our 5; surface type is a bonus head). Keep share-alike
   in mind for anything we publish built on it.
3. **SurfaceAI's aggregation recipe** (image → way, handling multiple surfaces per way) — compare
   with `backend/config/segment_aggregation.json`.
4. **Map our RQI to OSM `smoothness`** (5→excellent, 4→good, 3→intermediate, 2→bad,
   1→very_bad) so a GraphHopper custom model or BRouter profile can route on it, and so OSM
   tags become a feature/fallback where we have no frames.
5. **Accelerometer phase:** follow Roadroid/RoadLab: fixed mount, eIRI per 100 m, speed
   normalisation; IRI ↔ smoothness bands are discussed in the OSM community.
6. **RDD2022** only for the YOLO defect-polygon card, not the RQI model.

**Partnerships / community**
- **Járókelő:** link "report this pothole" from our segment card to Járókelő; ask for
  pothole report locations to cross-check our bad segments (they already partnered with
  Mapillary once).
- **OSM-HU community (talk-hu, StreetComplete users):** offer our map as a *hint layer* for
  human survey; never auto-import AI grades into OSM (AI edits are against community norms).
- **Academia:** BME (Barsi Á.) and SZTAKI have road-defect work; a thesis student could own
  the accelerometer study or a Magyar Közút validation.
- **Volunteer drivers:** the vialytics/Blyncsy lesson — ride on vehicles that drive anyway
  (couriers, taxi, municipal fleets) rather than asking people to make special trips.

**Risks**
- **Google Maps Platform ToS (biggest):** the terms forbid scraping/exporting Google Maps
  Content and creating content based on it; a third-party summary says they now also ban using
  it to train/validate ML models (**exact current wording not confirmed — read the official
  terms**). Our model is trained on Street View frames and publishes derived scores. Mitigation:
  legal read before any growth/monetisation; build a **Mapillary (CC BY-SA)** imagery path and own
  phone captures so the model doesn't depend only on Google imagery. See
  [PUBLISH_PLAN.md — Google ToS note](PUBLISH_PLAN.md#shared-google-tos-note).
- **Staleness:** Street View in Hungary is refreshed every few years (new drive announced 2026);
  winter 2025/26 created 26k potholes in Budapest alone. Show capture date per segment.
- **Big players:** Google/Waze could ship pothole-aware routing (Google holds a patent; Waze has
  the Waymo feed in the US). Our niche is Hungary, transparency and OSM-compatibility.
- **Licence contamination:** CC BY-SA / ODbL inputs make derived *datasets* share-alike; keep a
  record of which sources feed which published layer.
