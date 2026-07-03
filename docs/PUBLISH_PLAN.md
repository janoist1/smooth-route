# Publikálási terv — kétkörös: read-only publikálás, majd user-beküldés

*Állapot: **ÁTTERVEZVE (2026-07-03).** Kulcsdöntés: az elemzést első körben
**lokálisan, kérésre** futtatjuk → a publikus oldalnak nincs szüksége futó
backendre. Ezért **round 1 = read-only publikálás** (Vercel + Neon + Street
View deep-linkek; se torch, se worker, se prod-auth), és a korábban tervezett
auth/queue/kvóta átkerül **round 2-be** (user-beküldés). A már kész F1 (Clerk
auth) és F1.5 (minőség-rács) a repóban marad, round 2-ig a prod-on inaktív.
Árak ellenőrizve: 2026-07-03, források a végén.*

## Publikálási stratégia — két kör

**Round 1 — read-only publikálás (most).** Te futtatod az elemzést a saját
gépeden (a meglévő teljes pipeline: Google-letöltés + DINO-RQI), kérésre. Az
eredményt (pont-paraméterek + RQI-score-ok) egy `publish` scripttel feltöltöd
egy hostolt read-only DB-be. A publikus oldal csak **olvas**: térkép,
minőség-rács, útvonal-megjelenítés. **Kép nem kerül a felhőbe** — a
részletnézet egy ingyenes Google Maps Street View deep-linket ad (lásd
[Adatmodell](#adatmodell-változások-vázlat) + [ToS](#-google-tos-megjegyzés-őszintén)).
Nincs publikus user-akció → **nincs prod-auth, queue, kvóta.**

**Round 2 — user-beküldés (később).** Amikor kinyitod, hogy user is kérhessen
A→B elemzést: reaktiválod a kész **F1 Clerk-autht** + a **kérvény-flow-t**
(admin jóváhagyás → job → email) + **kvótákat**. Ehhez kell egy always-on
backend (torch + worker) — az alábbi Hetzner/Procrastinate/Clerk/R2 elemzés
**erre a körre** vonatkozik.

## Round 1 architektúra (TL;DR)

```
 [A Mac-ed: teljes pipeline]                (lokális, kérésre, Google-ingyenkeret alatt)
  Google-letöltés + DINO-RQI  ──publish──▶  [Neon Postgres]  (read-only adat)
  (a képek a gépeden maradnak)                    ▲
                                                  │ olvasás
                            ┌─────────────────────┴────────────┐
  böngésző ────────────────▶│ Vercel                           │
                            │ frontend (Vite) + read-only       │
                            │ /graphql serverless (torch-mentes)│
                            └───────────────────────────────────┘
  részletnézet ──▶ ingyenes Google Maps Street View deep-link (nincs tárolt kép)
```

| Réteg (round 1) | Választás | Havi költség |
|---|---|---|
| Frontend + read-API | Vercel (Hobby) | 0 $ |
| Read-only DB | Neon (free tier, PostGIS, scale-to-zero) | 0 $ |
| Compute (elemzés) | a saját géped, kérésre | 0 $ |
| Képek | **nincs tárolás** — Street View deep-link | 0 $ |
| Google Maps | ingyenkeret alatt (letöltés lokálisan; Directions proxyzva) | 0 $ |
| Domain | `simaut.hu` | ~1 €/hó |
| **Összesen** | | **~1 €/hó** |

A korábbi always-on stack (Hetzner + Procrastinate + Clerk + R2) **round 2-re**
marad — az alábbi részletes indoklás arra a körre érvényes.

## Cél

A Kátyúőr publikálása úgy, hogy **olcsó** (cél: ≤ ~10 €/hó fix költség) és
**technikailag rendben van** (nincs otthoni gép/tunnel, nincs adatvesztés,
nem lehet költséget robbantani). Ami ehhez most hiányzik:

| Hiányzó képesség | Ma | Cél |
|---|---|---|
| Felhasználókezelés | nincs (minden endpoint nyitott) | regisztráció + Google login |
| Jogosultsági szintek | nincs | `user` / `admin` (+ opcionális anonim olvasás) |
| Userhez kötött jobok | `jobs` tábla van, de user nélkül, in-process thread | perzisztens queue, user_id-val |
| Központi gyűjtés, dedup | minden kérés újra letölt/elemez | pano-alapú + térbeli dedup, 0 ismételt Google-hívás |
| Letöltési limit / költségvédelem | nincs | user-kvóta + globális havi keret + GCP-oldali kemény plafon |
| Éles infrastruktúra | lokális `make dev` / dev-Docker | VPS + CDN + objektumtár + CI-deploy |

## Round 2 architektúra (always-on backend — user-beküldéshez)

*Ez a felállás a **round 2**-re kell (amikor user is indíthat elemzést). Round
1-hez NEM — ott a fenti Vercel + Neon read-only stack fut.*

```
                ┌─────────────────────┐
   böngésző ───▶│ Cloudflare Pages    │   React/Vite build (ingyen)
                │ (frontend, statikus)│
                └────────┬────────────┘
                         │ HTTPS (api.<domain>, CF proxy előtte)
                ┌────────▼─────────────────────────────────────┐
                │ Hetzner VPS (1 gép, docker compose)          │
                │  ┌───────┐ ┌──────────┐ ┌────────┐ ┌───────┐ │
                │  │ Caddy │→│ API      │ │ Worker │ │PostGIS│ │
                │  │ (TLS) │ │ (FastAPI)│ │(torch, │ │       │ │
                │  └───────┘ └────┬─────┘ │ queue) │ └───▲───┘ │
                │                 └────────┴───┬────┴─────┘    │
                └───────────────────────────────┼──────────────┘
                          Procrastinate queue = ugyanez a Postgres
                         │                          │
                ┌────────▼────────┐        ┌────────▼────────┐
                │ Clerk (auth)    │        │ Cloudflare R2   │
                │ email+jelszó +  │        │ képek + DB-     │
                │ Google OAuth    │        │ backup (10GB    │
                │ (50k user ingyen)│       │ ingyen, 0 egress)│
                └─────────────────┘        └─────────────────┘
```

| Réteg | Választás | Havi költség |
|---|---|---|
| Frontend | Cloudflare Pages | 0 € |
| API + worker + DB | Hetzner VPS CX32 (4 vCPU / 8 GB) | ~6,80 € |
| Auth | Clerk Free (50 000 MRU-ig ingyen, 2026. febr. óta) | 0 € |
| Képek + backup | Cloudflare R2 (10 GB ingyen, egress mindig 0) | 0 € |
| Queue | Procrastinate (a meglévő Postgresen fut) | 0 € |
| Google Maps | kvótákkal a free tier **alatt** tartva | 0 € (felette: 7 $/1000 kép) |
| Domain | .eu / .app / .hu | ~1 €/hó |
| Sentry + UptimeRobot | free tier | 0 € |
| **Összesen** | | **~8 €/hó** |

Szűkebb büdzsére: CX22 (2 vCPU / 4 GB, ~4 €/hó) is elindul, de a torch-inferencia
mellett a Postgresszel együtt szoros; Hetzneren a felméretezés pár kattintás,
lefelé viszont a lemez miatt nem megy — ezért érdemes CX22-vel indulni **kis
lemezzel** vagy rögtön CX32-vel.

## Miért ez, és miért nem a többi

### Hoszting

A döntő tényező: a backend futásideje **torch + transformers + ultralytics**
(~5–7 GB image, 2–4 GB RAM inferencia alatt), PostGIS-t igényel, és hosszú
háttér-jobokat futtat. Ez **kizárja a serverless/edge platformokat** a nehéz
részre — a Vercel/Lambda függvényméret- és futásidő-limitjei miatt.

| Opció | Havi költség | Értékelés |
|---|---|---|
| **Hetzner VPS (compose: Caddy+API+worker+PostGIS)** ✅ | ~4–7 € | Legolcsóbb *és* legnagyobb kontroll. Ár: a Postgrest te üzemelteted → automatizált backup kötelező (F6). Ár-teljesítményben verhetetlen. |
| Supabase (DB+auth+storage) + Fly.io worker | 0–25 $+ | A free Supabase-projekt **7 nap DB-inaktivitás után leáll** (kézzel kell éleszteni) — publikált appnál ez uptime-kockázat; az 1 GB storage a képeknek már ma kevés (1,1 GB). A Fly-on egy always-on 4 GB-os worker önmagában drágább, mint az egész Hetzner-gép. |
| AWS (Cognito+SQS+ECS/Fargate+RDS) | ~30–50 $ | Mindent tud, de RDS+Fargate always-on önmagában többszöröse a célbüdzsének, és a legtöbb ops (IAM, VPC, ECR…). Akkor éri meg, ha AWS-tudást akarsz építeni — költségben nem versenyző. |
| Render / Railway | ~10–25 $ | Egyszerű deploy, de a torch-hoz elég RAM-os csomag már drágább a Hetznernél, kevesebb kontrollal. |
| Otthoni gép + tunnel | 0 € | Kizárva (a géped uptime-ja = az app uptime-ja). A "keresztszolgáltatásos alagút" (pl. Cloudflare Tunnel egy VPS-ről) valós minta, de ha már van publikus IP-jű VPS-ed Caddy-vel, nincs rá szükség — helyette az ingyenes **CF proxy** (narancs felhő a DNS-ben) kerül a VPS elé: WAF, DDoS-védelem, cache, és az origin IP elrejtése ingyen. |

### Auth

Saját auth írása (jelszó-hash + JWT + Google OAuth + email-verifikáció +
jelszó-reset + session-kezelés) hetekbe kerül és biztonsági felelősség — nulláról
indulva providert érdemes használni.

| Opció | Free tier | Értékelés |
|---|---|---|
| **Clerk** ✅ | 50 000 MRU (2026. febr. óta; utána Pro 20 $/hó) | Kész React `<SignIn/>`/`<SignUp/>` komponensek, Google OAuth kattintásra, **az emaileket (verifikáció, reset) is ő küldi** — nem kell SMTP-t sem beállítani. A backend csak JWT-t ellenőriz (JWKS). A legkevesebb munka. |
| Supabase Auth | 50k MAU | Csak akkor éri meg, ha a DB is ott van — de a DB-t a VPS-re tettük (pause-kockázat + méretlimit), így nem. |
| Firebase Auth | ~korlátlan ingyen | Sosem "pause"-ol, de UI-t magadnak kell építeni, és több integrációs munka. B-terv, ha a Clerk árazása később elszállna. |
| FastAPI-Users (self-host) | 0 € | Nincs vendor lock, de email-infra + Google OAuth + biztonsági karbantartás a tiéd. Nem éri meg elsőre. |

**Lock-in védelem:** a backend csak annyit tud a Clerkről, hogy "JWT → `clerk_id`".
A saját `users` táblánk a forrása mindennek (role, kvóta, jobok) — providert
váltani = egy JWT-verifikáló dependency cseréje.

### Queue

| Opció | Értékelés |
|---|---|
| **Procrastinate (Postgres-alapú)** ✅ | Nincs új infra — a queue **ugyanaz a Postgres**, ami már megvan. LISTEN/NOTIFY (azonnali pickup), retry, lock, periodikus taskok, sync+async. Aktívan karbantartott (utolsó release: 2026. jún.). Tranzakcionális enqueue: a job és a domain-adat egy commitban. |
| Redis + Celery/RQ | Plusz egy Redis-konténer (RAM + üzemeltetés) olyan volumenért, ami Postgresen is elfér. Később, ha tényleg kellene (nem valószínű). |
| AWS SQS | Önmagában majdnem ingyen, de behúzza az AWS-account/IAM-üzemeltetést egyetlen queue-ért. Nem éri meg. |
| Marad a `threading.Thread` | Kizárva: API-restartkor elhal a job, nincs retry, nem skálázható, és a worker (torch) nem választható le az API-ról. |

### Google Maps költségmodell — a terv sarokköve

Ellenőrzött tények (2026-07, hivatalos árlista):

- **Street View Static (kép): 7 $/1000 kérés, havi 10 000 ingyen** (Essentials).
- **Street View Metadata: INGYENES, korlátlan.** Ez adja vissza a `pano_id`-t
  fizetés *nélkül* → a dedup erre épül.
- **Directions/Routes: 5 $/1000, havi 10 000 ingyen.**
- A GCP-konzolban **API-nkénti napi kvótaplafon** állítható → ez a *kemény*
  költségplafon, akkor is véd, ha az app-oldali limit hibázna.

Következmény: ha a globális havi keretet a free tier **alá** lőjük be (pl.
9 000 új kép/hó), a Google-költség **0 $**, és e fölé csak tudatos döntéssel
mehetünk.

## Központi gyűjtőszolgáltatás — dedup-terv

Ma minden route-kérés újra letölti és újraelemzi a pontjait. A cél: egy pont
képét **pontosan egyszer** fizetjük meg, userek között megosztva.

Háromszintű dedup:

1. **Pano-szintű (az igazi kulcs).** A Street View-nak saját panoráma-azonosítója
   van (`pano_id`). Új pont feldolgozása előtt **ingyenes** metadata-hívással
   lekérjük a pano_id-t; ha `(pano_id, heading_bucket)` már létezik nálunk
   (heading 15°-os vödrökre kerekítve), a meglévő képet/elemzést használjuk.
   Fizetős képlekérés csak tényleg új panorámára megy ki.
   → új oszlop: `street_view_images.pano_id` (+ unique index a párra), backfill
   ingyenes metadata-hívásokkal.
2. **Térbeli (PostGIS).** Route-gyűjtéskor a generált mintavételi pontok előtt
   lekérdezzük a már meglévő pontokat a nyomvonal ~10 m-es sávjában (heading
   ±30°) — ezekre metadata-hívás sem kell.
3. **Konkurencia.** Két user egyszerre kéri ugyanazt az utcát → a worker
   `INSERT … ON CONFLICT DO NOTHING`-gal "claimeli" a pano-kat, és
   `SELECT … FOR UPDATE SKIP LOCKED`-del dolgozza fel; kezdetben 1 worker-process
   fut, így ez triviálisan biztonságos, de a séma később több workert is kibír.

**Újraelemzési szabály:** az elemzés eredménye mellé `model_version` kerül
(az RQI-artifact verziója). Új modell élesítésekor (ml/ kapu után) egy
admin-indította batch-job elemzi újra a meglévő képeket — *letöltés nélkül*.

## Kvóták és költségvédelem

Rétegek (kívülről befelé):

1. **GCP-oldali kemény plafon:** napi kvóta a Street View Static + Directions
   API-ra (pl. 300 kép/nap) + budget alert. Ez akkor is fog, ha az app hibázik.
2. **Globális havi keret az appban:** pl. 9 000 új kép/hó (free tier alatt).
   A worker minden batch előtt ellenőrzi; betelt keretnél a job "kvótára vár"
   státuszba megy, nem hal el.
3. **Per-user kvóta:** csak az *új* (nem dedupolt) letöltés számít bele! Pl.
   alapértelmezés 100 új kép/nap és 1 000/hó; admin korlátlan. A meglévő
   settings-rendszerben (`core/settings_registry.py`) konfigurálható.
4. **API rate limit:** slowapi (per-user/per-IP) a mutációkra + a CF proxy
   ingyenes rate-limit szabálya a nyers kérésszintre.

Könyvelés: `usage_events` tábla (user_id, kind: `sv_image_fetch` |
`directions_call` | `analysis`, qty, job_id, created_at). Ebből jön a
kvóta-ellenőrzés, a UI-n a "ennyi maradt ma" kijelzés és az admin usage-nézet.

## Jogosultsági szintek

| Szerep | Mit tehet |
|---|---|
| anonim *(opcionális, döntést igényel)* | publikus térkép megtekintése (cache-elt, read-only aggregált végpont) |
| `user` (regisztrált) | térkép + route-gyűjtés indítása (kvótával), saját jobjai listája/állapota |
| `admin` | minden: címkézés/review UI, training, settings, összes job, kvóta-felülbírálás, usage-nézet |

Fontos: a **címkéző/training felületek ma teljesen nyitottak** — publikáláskor
ezek admin-only-k lesznek (a címkeminőség a modell alapja, nem lehet publikus).

## Adatmodell-változások (vázlat)

```sql
-- új
users(id uuid PK, clerk_id text UNIQUE, email text, role text DEFAULT 'user',
      created_at timestamptz)
usage_events(id bigserial PK, user_id uuid FK, kind text, qty int,
             job_id text NULL, created_at timestamptz)  -- index: (user_id, created_at)

-- bővítés
jobs        + user_id FK, job_type text, params jsonb   -- round 2 (userhez kötés)
street_view_images
            + pano_id text (index)          -- ROUND 1: a Street View deep-linkhez
            + heading_bucket smallint        -- round 2 (dedup)
            + model_version text
            + UNIQUE (pano_id, heading_bucket)  -- round 2 (dedup)
```

**Round 1 — Street View kép helyett link.** A `pano_id`-t előrehozzuk (a
metadata-hívás úgyis visszaadja, csak eddig nem mentettük). A publikus DB-be
**nem kerül kép**; a részletnézet egy ingyenes Google Maps deep-linket épít:
`https://www.google.com/maps/@?api=1&map_action=pano&pano=<pano_id>&heading=<h>&pitch=<p>`
(fallback `viewpoint=<lat>,<lng>`). Fontos: a Street View **Static URL-t NEM**
tesszük `<img>`-be — az megtekintésenként számlázna és a kulcsot is kiadná. A
lokális elemzés továbbra is letölti a képet a pixelhez, de az a gépeden marad.

A séma Alembic-migrációkkal jön (`backend/alembic/`, F1-gyel bevezetve); a
`create_all` már kikerült.

## Biztonsági hardening (publikálás előtt kötelező)

- [ ] CORS: a `"*"` kivétele (`backend/app/main.py:19`), csak a frontend domén.
- [ ] GraphQL: introspection + GraphiQL kikapcsolása prodban; a
      `strawberry-graphql[debug-server]` extra csak dev-dependency legyen.
- [ ] Dockerfile: `--reload` ki a CMD-ből, non-root user, multi-stage build,
      pinelt dependenciák (lockfile — pl. `uv lock`).
- [ ] Google-kulcs: szerveroldali kulcs **IP-restrikcióval** (VPS IP-je),
      napi API-kvótaplafon + budget alert a GCP-ben.
- [ ] Secrets: a VPS-en `.env` (600-as jogosultság), sosem a repóban; a CI-ben
      GitHub Secrets.
- [ ] Debug `print`-ek helyett strukturált logging (a `job_service.py` tele van
      `print("DEBUG: ...")`-gal).
- [ ] REST `/api/v1/*` végpontok auth mögé (ugyanaz a JWT-dependency, mint a
      GraphQL-nél).

## ⚠️ Google ToS-megjegyzés (őszintén)

A Google Maps Platform ToS a Street View-tartalom **tartós tárolását/cache-elését
korlátozza**. A round-1 redesign ezt **elegánsan megkerüli**: a publikus oldalra
**nem kerül tárolt kép** — a részletnézet egy ingyenes Google Maps Street View
**deep-linket** ad (a user a Google saját felületén nézi). Így:

1. a publikus felület a **származtatott adatot** (RQI-szín, minőség-rács,
   statisztika) mutatja + linket a Street View-ra — nincs tárolt/újraterjesztett
   Google-kép;
2. a Street View **Static URL nem megy `<img>`-be** (az megtekintésenként
   számlázna + kulcsot szivárogtatna);
3. a lokálisan letöltött képek (a training alapja) a **saját gépeden** maradnak,
   nem publikusak.

Round 2-ben, ha inline kép/pano kell: a hivatalos **Street View embed** (Maps JS
`StreetViewPanorama`, ingyen ≤ 5k megnyitás/hó) a ToS-tiszta út — nem a tárolt
kép újraterjesztése.

## Fázisok — megvalósítható lépések

Minden fázis önállóan shippelhető, a végén zöld kapukkal
(`pytest` + `typecheck/lint/test`, ld. [AGENTS.md](../AGENTS.md)). Egy fázis =
egy-két AI-session (promptok: [SESSION_PROMPTS.md](SESSION_PROMPTS.md)).

> **Két csoport:** a **Round 1** fázisok (R1.1–R1.5) a soron következő munka
> (read-only publikálás). Az alábbi **F0–F6** a **Round 2** (always-on backend,
> user-beküldés) — kivéve az **F1** (Clerk auth) és **F1.5** (minőség-rács),
> amelyek KÉSZEK és a repóban maradnak, round 2-ig a prod-on inaktívak.

## Round 1 fázisok — read-only publikálás

**Deploy-topológia (eldöntve): két külön Vercel-projekt.**

```
  simaut.hu       → Vercel projekt #1  (root: frontend/)  — Vite SPA
  api.simaut.hu   → Vercel projekt #2  (root: backend/)   — Python, read-only
                         │
                         ▼
                    [Neon Postgres]  ◀── publish script (a Mac-edről)
```

A frontend a `VITE_API_URL`-en (`https://api.simaut.hu`) hívja a `/graphql`-t
(dev-ben üres → relatív, Vite-proxy a :8000-re). A backend UGYANAZ a
`app.main:app`, csak `PUBLIC_READ_ONLY=1` env-vel → query-only séma. Ez a
kétprojektes felállás elkerüli a monorepo-import gubancot; local dev
változatlan (a flag default `False`).

### R1.1 — Street View link a tárolt kép helyett (KÉSZ, `1f10b25`)

- [x] `pano_id` oszlop (Alembic 0003) + a `collect_points` menti
      (a `generate_street_view_metadata` már visszaadta).
- [x] `Point.streetViewUrl` számított mező (`api=1&map_action=pano&pano=…`,
      fallback `viewpoint=lat,lng`); a `PointDetailCard` „Megnyitás Street
      View-ban" linket renderel, nem tárolt `<img>`-et.
- **Elfogadás:** a link a helyes panorámára visz; nincs tárolt kép a publikus
      úton; kapuk zöldek. ✓

### R1.2 — Read-only mód + Vercel-csomagolás (KÉSZ kód: `63c1dd2` + deploy-artefaktumok)

- [x] `PUBLIC_READ_ONLY` flag: `main.py` a `read_schema`-t (query-only) mountolja,
      CORS `ALLOWED_ORIGINS`-ra szűkül; `getRoute` anonim read-only módban
      (`IsAuthenticatedUnlessPublicRead`). Torch-mentes import — igazolva.
- [x] `backend/requirements.txt` (torch-mentes), `backend/api/index.py` ASGI
      entrypoint, `backend/vercel.json` (`@vercel/python`), `frontend/vercel.json`
      (SPA rewrite), `VITE_API_URL` a kliensben.
- **Deploy-env a Vercel projekt #2-n:** `PUBLIC_READ_ONLY=1`,
      `RUN_MIGRATIONS_ON_STARTUP=false`, `DATABASE_URL=<neon>`,
      `GOOGLE_MAPS_API_KEY=<kulcs>`, `ALLOWED_ORIGINS=https://simaut.hu`.
- **Elfogadás:** a read-only app anonim kiszolgálja a `points`/`roadQualityGrid`/
      `point` lekérdezéseket, mutációt elutasít, torch nélkül importál. ✓
      *(Vercel-deploy = a te lépésed: `vercel` a `backend/`-ben és a `frontend/`-ben.)*

### R1.3 — Neon + publish script (KÉSZ script; Neon-projekt = a te lépésed)

- [x] `backend/scripts/publish.py` (egy parancs): a target sémát alembic-kel
      felhúzza (fresh Neon-on `CREATE EXTENSION postgis` + táblák), majd a lokális
      `street_view_images` publikus oszlopait **full-replace**-eli a targetbe;
      `image_url` + `location` NULL-ra (a publikus DB csak a Street View linkhez
      kell). A target a `PUBLISH_DATABASE_URL` env-ből (soha a repóba). Lokálisan
      scratch DB ellen tesztelve: 17 607 sor átment, a read-API hibátlanul adta a
      `points`/`roadQualityGrid`/`streetViewUrl`-t. **Neon támogatja a PostGIS-t.**
- [ ] Neon-projekt létrehozása (EU-régió), a connection string a Vercel-backend
      `DATABASE_URL`-jébe + a lokális `publish` `PUBLISH_DATABASE_URL`-jébe.
- **Használat:** `cd backend && PUBLISH_DATABASE_URL='postgresql://…neon…'
      ../.venv/bin/python scripts/publish.py`
- **Elfogadás:** lokális elemzés után egy `publish` futtatás → a publikus térképen
      megjelenik az új adat. ✓ (a script-lánc lokálisan igazolva)

### R1.4 — DNS + deploy + hardening-zárás (becslés: 0,5–1 nap)

- [ ] DNS: `simaut.hu` + `www` → Vercel projekt #1; `api.simaut.hu` → Vercel
      projekt #2 (Vercel adja a CNAME/A célt); a `sim.hu`-regisztrátornál v.
      Cloudflare-en.
- [ ] Google-kulcs IP-/referrer-restrikció + GCP budget-alert; GraphQL
      introspection off prodban (round-1 nice-to-have).
- **Elfogadás:** a `simaut.hu` publikusan kiszolgálja a read-only térképet;
      a Directions az `api.simaut.hu` proxyn át megy; nincs kiszivárgó kulcs.

*(Round 1-hez NEM kell: Dockerfile/worker/queue, Clerk a prodban, R2, kvóták.)*

## Round 2 fázisok — user-beküldés (always-on backend)

### F0 — Prod-alapozás (becslés: 1–2 nap)

- [x] Alembic bevezetése; baseline migráció a mostani sémáról; `create_all`
      csak tesztben. *(F1-gyel együtt kész: `backend/alembic/` — 0001 baseline
      + 0002 users; startupkor `ensure_database_schema()` fut pg_advisory_lock
      alatt, a pre-Alembic DB-t automatikusan stampeli. A `create_all` kikerült
      a main.py-ból.)*
- [ ] Prod-konfig a pydantic-settings-ben: `ENV=prod` esetén CORS-szűkítés,
      introspection/GraphiQL off, debug-logok ki.
- [ ] Dockerfile prod-osítása (multi-stage, non-root, no `--reload`) + külön
      `docker-compose.prod.yml` (api + worker + db + caddy).
- [ ] `print` → `logging` csere a services rétegben.
- **Elfogadás:** a prod-compose lokálisan felállva kiszolgálja a frontend
  buildet; kapuk zöldek.

### F1 — Auth és szerepek (Clerk) (becslés: 2–4 nap)

- [x] Clerk-app létrehozása (email+jelszó és Google provider bekapcsolása;
      Google Cloud OAuth consent + client id). *(Dev-instance él:
      `relieved-calf-51`; kulcsok a gyökér `.env`-ben (`CLERK_SECRET_KEY`,
      `CLERK_ISSUER`, `AUTH_MODE=clerk`) és `frontend/.env`-ben
      (`VITE_CLERK_PUBLISHABLE_KEY`). Devben a Google a Clerk közös
      OAuth-kliensével megy; a SAJÁT Google Cloud consent + client id majd a
      prod-instance-hoz kell (F5).)*
- [x] Frontend: `@clerk/clerk-react` — `<SignIn/>`, `<SignUp/>`, user-menü;
      Apollo authLink a Clerk session-tokennel. *(`frontend/src/modules/auth/`;
      SignInButton modálban adja a SignIn/SignUp-ot; admin-menük és -útvonalak
      a `me` query szerepe alapján rejtve/átirányítva.)*
- [x] Backend: JWT-verifikáló dependency (JWKS, `clerk_id` kinyerés);
      `users` tábla + JIT-provisioning (első kérésnél sor jön létre);
      `role` oszlop (`user`/`admin`; admin kézzel/SQL-lel állítva).
      *(`app/core/auth.py`; users tábla a 0002 migrációban. Figyelem: a Clerk
      default session-token NEM tartalmaz emailt — vagy JWT-template-tel kell
      hozzáadni a dashboardon, vagy a backend a Clerk API-ból tölti be
      `CLERK_SECRET_KEY` birtokában.)*
- [x] Strawberry permission-osztályok: `IsAuthenticated`, `IsAdmin`; a
      training/review/settings mutációk admin-only; route-indítás user-only.
      *(Plusz: a training/settings QUERY-k is admin-only-k, a `getRoute` query
      IsAuthenticated — fizetős Directions-hívás; új `me` query a frontendnek.)*
- [x] REST végpontok ugyanezzel a dependency-vel védve. *(A két mutáló végpont
      — `POST /process-route`, `POST /job/{id}/stop` — user-only; a GET-ek
      (points, job-status, SSE) anonim térkép-olvasásként nyitva maradtak,
      F2-ben kötődnek userhez.)*
- [x] Döntés + implementáció: anonim térkép-olvasás engedett-e (ha igen: csak
      a cache-elt aggregált végpont). *(Igen — a pont-olvasó GraphQL/REST
      végpontok anonimok; a `settings` query viszont admin lett, a térkép
      kliensoldali defaultokkal fut anonim módban.)*
- **Elfogadás:** token nélkül a védett műveletek 401-et adnak ✓ (teszt +
  élő próba); user nem éri el az admin-felületeket ✓ (403/FORBIDDEN valódi
  user-tokennel + UI-rejtés); jelszavas login böngészőben végig E2E ✓
  (teszt-user: `janoist1+clerk_test@gmail.com`, admin-ra promótálva; új
  eszközről a Clerk email-kódot kér — teszt-címen fixen 424242); Google-login
  gomb él, *egy kézi átkattintás-teszt van hátra*.

### F1.5 — Térkép minőség-rács: „őszinte kép egyben" (KÉSZ, 2026-07-03)

Termékdöntés-blokk (megbeszélve): anonim térkép-olvasás; a „kerülés" v1-ben csak
figyelmeztetés (nincs aktív újratervezés); a lefedettség-bővítés kérvény-alapú
(ld. F2). Ez az elem a mostani **pont-levágás bugot** (limit=2000) javítja és
egyben a kért „őszinte kép az úthálózatról egyben" feature-t adja.

**Fontos tanulság (leaflet.heat zsákutca):** először klasszikus hőtérképet
csináltunk (leaflet.heat), de az **összeadja az egymásra eső pontok
intenzitását** → a sűrűn mintázott (de jó) utak felizzottak, vagyis a szín a
*lefedettséget* kódolta, nem a minőséget. A helyes megjelenítés **cellánkénti
ÁTLAG-RQI** (sűrűségtől független): egy sűrűn mintázott jó út zöld marad.

- [x] Backend: `roadQualityGrid(zoom, bbox)` GraphQL query — zoom-függő rács
      (`floor(lat/cell), floor(lng/cell)`), cellánként az **átlag-RQI**; válasz
      `{cell, cells: [[swLat, swLng, avgRqi], …]}` (kompakt, cella SW-sarok +
      átlag). Effektív pont = `COALESCE(dino_rqi_score, rqi_score)`. Anonim
      (mint a `points`). Tiszta helperek (`app/services/map_aggregation.py`),
      unit-tesztelve. Élőben: Törökbálint (zoom 13) átlagai 1.0–1.58 → zöld.
- [x] Frontend: egyetlen **canvas-réteg** (`QualityGridLayer`, nem additív) —
      minden cella az átlag-RQI-ja szerint színezve (`getRQIColor`: ≤2 zöld,
      ≤3 sárga, ≤4 piros), áttetszően. Zoom < 14 → rács, ≥ 14 → nyers
      (kattintható) pontok; a router-saga és a job-utáni refresh zoom-tudatos.
      A **szín = minőség, a kitöltött cellák = lefedettség** (nem a szín ereje).
      Böngészőben igazolva: Törökbálint zöld (a heat-verzióban tévesen narancs
      volt), Budapest-belváros piros góc (valódi rossz utak).
- [x] Mellékesen javított latens bug: a `getPreloadedState` (store.ts) részleges
      `map` slice-ot épített, ami elnyelte az új mezőket (crash `undefined.map`);
      most a teljes `initialState`-et teríti, csak a viewportot írja felül.
- [x] Ráközelített (zoom ≥ 14) pont-nézet levágás javítva: a `points` lekérés
      limitje 2000 → 20000 (a kicsi viewport-bbox a valódi korlát; sűrű
      belvárosi z=14 nézet ~2300 pont), és a pontok `preferCanvas`-szal
      canvasra renderelnek (több ezer pont is gyors). Böngészőben igazolva:
      Budapest-belváros z=14 → mind a ~2286 pont látszik, hézag nélkül.
- **Elfogadás:** kizoomolt országnézet nem vág le pontot, minőség-színezett
  rácsot mutat (sűrűségtől független); ráközelítve MINDEN pont látszik
  (nincs 2000-es levágás); kapuk zöldek (backend 64, frontend
  typecheck/lint/16). ✓
- *Nyitott finomítás (opcionális):* a rács kissé „blokkos"; egy canvas-upscale
  + blur simábbá tenné a minőség-felület megtartásával.

### F2 — Kérvény-alapú lefedettség-bővítés + userhez kötött jobok (becslés: 3–4 nap)

Modellváltás (megbeszélve): a drága lefedettség-bővítés (új A→B képgyűjtés +
inferencia) **nem önkiszolgáló kvótával**, hanem **kérvény→admin-jóváhagyás→
email-értesítés** folyamattal megy — kevesebb visszaélési felület, a Google-
költség admin-kézben. A mindennapi útvonal-tervezés a *már elemzett* utakon
önkiszolgáló marad (bejelentkezve).

- [ ] `analysis_request` tábla (Alembic migráció): `user_id` FK, `origin`,
      `destination`, `status` (`pending`/`approved`/`running`/`done`/`rejected`),
      `note`, `job_id` NULL, `created_at`.
- [ ] **Magyar geofence** (v1: bounding box, később országhatár-poligon):
      a beküldés és a `getRoute` elutasítja a nem magyar A/B-t. Egyelőre a nem
      magyar útvonal-hozzáadás tiltva (termékdöntés).
- [ ] GraphQL: `submitAnalysisRequest(origin, destination, note)` (user, geofence-
      elt), `myRequests` (user), `pendingRequests` + `approveRequest`/
      `rejectRequest(reason)` (admin). Elfogadás indítja a meglévő process-route
      jobot; a job `user_id`/`request_id`-hez kötve.
- [ ] Procrastinate behúzása; worker belépési pont (külön konténer ugyanabból
      az image-ből, más CMD).
- [ ] A `tasks.py`/`job_runner.py` thread-indítás lecserélése `defer`-re; a
      pipeline-lépések (collect → download → analyze) taskokként, retry-vel.
- [ ] `jobs` tábla bővítése: `user_id`, `job_type`, `params`; a meglévő
      SSE-progress megtartása (a domain-jobs tábla frissül, mint eddig).
- [ ] Egyidejűség: worker konkurencia = 1 induláskor (a torch-inferencia úgyis
      soros); a queue-séma többet is kibír később.
- [ ] **Email-értesítés** a kérvény elkészültekor: pluggable provider env-ből
      (SMTP vagy pl. Resend API-kulcs; titok SOSEM a repóba), konzol-fallback
      dev-hez. A job befejezésekor a kérelmező kap egy „kész, megnézheted" mailt.
- **Elfogadás:** user beküld egy magyar A→B kérvényt (nem magyar → elutasítva);
  admin jóváhagyja → job lefut; a kérvény `done`-ra vált, a kérelmező email-
  értesítést kap (F2-email); API-restart közben futó job túléli és befejeződik.

### F3 — Központi gyűjtés: dedup + kvóták (becslés: 3–5 nap)

- [ ] `pano_id` + `heading_bucket` + `model_version` oszlopok; unique index;
      **backfill** a meglévő ~1900 képre ingyenes metadata-hívásokkal.
- [ ] Letöltés-út átalakítása: metadata-first (ingyen) → csak új
      `(pano_id, bucket)` esetén fizetős képlekérés.
- [ ] Térbeli reuse: route-sáv lekérdezés PostGIS-szel a pontgenerálás előtt.
- [ ] `usage_events` tábla + kvóta-szolgáltatás (user napi/havi, globális havi
      keret) a settings-rendszerbe kötve; betelt kvótánál a job vár, a user
      értelmes hibát/staust lát.
- [ ] Konkurencia-védelem: claim (`ON CONFLICT DO NOTHING`) + `SKIP LOCKED`.
- [ ] Frontend: kvóta-kijelzés (maradék napi keret), "ebből X pont már megvolt,
      Y új" visszajelzés a job-kártyán.
- **Elfogadás:** ugyanarra a szakaszra indított második job **0** fizetős
  Google-hívást generál; kvóta-túllépés blokkol és jól kommunikált.

### F4 — Képek R2-re (becslés: 1–2 nap)

- [ ] R2 bucket (privát) + boto3 S3-kliens; `image_url` → objektumkulcs.
- [ ] Migrációs szkript: a meglévő 1,1 GB `data/images/` feltöltése.
- [ ] Kiszolgálás: rövid életű presigned URL-ek bejelentkezett usernek
      (ld. ToS-szakasz); a worker elemzéskor letölt → elemez → lokálisan nem
      tart meg (vagy LRU-cache).
- [ ] Az ml/ pipeline továbbra is tud lokálisan dolgozni (sync szkript R2-ről).
- **Elfogadás:** friss deploy üres lemezzel is teljes funkcionalitású; a
  training-workflow működik R2-forrásból.

### F5 — Éles infra + CI/CD (becslés: 1–2 nap)

- [ ] Hetzner VPS (CX32; EU régió) + docker compose (caddy, api, worker, db,
      volume-ok); firewall: csak 80/443 + SSH.
- [ ] Domain + Cloudflare DNS **proxyval** (narancs felhő: WAF, rate-limit,
      origin-IP elrejtés — ez a "keresztszolgáltatásos alagút" helyes formája).
- [ ] Frontend: Cloudflare Pages, `VITE_API_URL` a prod API-ra; PR-preview
      buildek ingyen.
- [ ] CI/CD: GH Actions — a meglévő tesztkapuk után image build → GHCR →
      SSH-deploy (`docker compose pull && up -d`); Alembic migráció a deploy
      lépésben.
- [ ] Clerk prod-instance (saját domainen); GCP-kulcs IP-restrikció +
      napi kvótaplafonok élesítése.
- **Elfogadás:** éles URL TLS-sel; push a main-re → automatikus deploy; a
  staging (= lokális prod-compose) és az éles azonos image-ből fut.

### F6 — Üzemeltetés: backup + megfigyelhetőség (becslés: 1–2 nap)

- [ ] Éjszakai `pg_dump` → R2 (retenció: 14 nap) + **restore-próba
      dokumentálva** (backup, amit sosem próbáltál visszatölteni, nem backup).
- [ ] Hetzner snapshot heti cron (olcsó, gépszintű vész-visszaállítás).
- [ ] Sentry free tier (backend + frontend), UptimeRobot a `/health`-re.
- [ ] Admin usage-nézet: napi/havi Google-hívások, user-toplista, keret-állapot
      (egy GraphQL query + egyszerű táblázat elég).
- **Elfogadás:** restore-próba sikeres; riasztás jön le-/kieséskor; az admin
  látja, mennyi Google-keret fogyott.

**Teljes becslés: ~11–18 munkanap** (részidőben 3–5 hét), fázisonként
shippelhető állapotokkal.

## Nyitott kérdések (termékdöntések — a te döntésed)

1. **Anonim térkép:** legyen-e publikus (read-only, cache-elt) térképnézet
   login nélkül? *Javaslat: igen — ez a termék kirakata, és olcsó.*
2. **Kvótaszámok:** 100 új kép/nap/user és 9 000/hó globális jó kiindulás?
   (Free tier alatt = 0 $ Google-költség.)
3. **ToS-álláspont:** rendben van-e a "kép privát, származtatott adat publikus"
   irány (fenti 1+3)?
4. **Domain:** van-e már, vagy kell venni? (Clerk prod-hoz is kell.)

## Források (ellenőrizve: 2026-07-03)

- Google árlista (Street View Static 7 $/1k + 10k ingyen; **metadata: ingyen,
  korlátlan**; Directions/Routes 5 $/1k + 10k ingyen):
  [developers.google.com/maps/billing-and-pricing/pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
- Supabase free tier (500 MB DB, 50k MAU, 1 GB storage, **7 nap inaktivitás →
  pause**): [supabase.com/pricing](https://supabase.com/pricing)
- Hetzner Cloud árak (CX22 ~3,79 €; 2026.06.15-i árkorrekció!):
  [hetzner.com/cloud](https://www.hetzner.com/cloud/regular-performance) ·
  [árkorrekció](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
- Cloudflare R2 (10 GB ingyen, 0 egress):
  [developers.cloudflare.com/r2/pricing](https://developers.cloudflare.com/r2/pricing/)
- Clerk (free tier 50k MRU-ra emelve, 2026. febr.):
  [clerk.com/pricing](https://clerk.com/pricing)
- Procrastinate (Postgres-alapú queue, aktív, 2026. jún. release):
  [github.com/procrastinate-org/procrastinate](https://github.com/procrastinate-org/procrastinate)
