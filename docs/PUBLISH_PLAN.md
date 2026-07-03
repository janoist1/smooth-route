# Publikálási terv — auth, jobok, kvóták, deploy

*Állapot: **ELFOGADVA** (2026-07-03). Végrehajtási sorrend: az **F1 (user-modul)
előrehozva** — publikálás előtt lokálisan kifejlesztve derülnek ki a valós
szükségletek; az F0-ból csak az Alembic-baseline jön vele (séma-változás miatt).
Az árak/limitek ellenőrizve: **2026-07-03**, források a dokumentum végén.
Fázisok: [F0–F6](#fázisok--megvalósítható-lépések); session-promptok:
[docs/SESSION_PROMPTS.md](SESSION_PROMPTS.md).*

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

## A kiválasztott architektúra (TL;DR)

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
jobs        + user_id FK, job_type text, params jsonb   -- meglévő tábla marad
street_view_images
            + pano_id text (index), heading_bucket smallint,
            + model_version text
            + UNIQUE (pano_id, heading_bucket)
```

A séma ma `create_all`-lal jön létre (`backend/app/main.py:30`) — ez éles DB-nél
nem elég: **Alembic** kell (F0), első lépésként a mostani állapot baseline-jával.

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
korlátozza**. A pipeline ma is tárol képeket (ez a training alapja) — publikálva
ez láthatóbbá válik. Javasolt kockázatcsökkentés:

1. a tárolt képek **privátban maradnak** (R2 privát bucket, rövid életű presigned
   URL csak bejelentkezett usernek) — nincs publikus képgaléria;
2. a részletkártyán opcionálisan **élő Street View embed** a tárolt kép helyett;
3. a publikus felület a **származtatott adatot** (RQI-szín, statisztika) mutatja.

Ez termékdöntés — a terv az 1+3 kombinációval számol.

## Fázisok — megvalósítható lépések

Minden fázis önállóan shippelhető, a végén zöld kapukkal
(`pytest` + `typecheck/lint/test`, ld. [AGENTS.md](../AGENTS.md)). Egy fázis =
egy-két AI-session (promptok: [SESSION_PROMPTS.md](SESSION_PROMPTS.md)).

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

### F2 — Perzisztens queue + userhez kötött jobok (becslés: 2–3 nap)

- [ ] Procrastinate behúzása; worker belépési pont (külön konténer ugyanabból
      az image-ből, más CMD).
- [ ] A `tasks.py`/`job_runner.py` thread-indítás lecserélése `defer`-re; a
      pipeline-lépések (collect → download → analyze) taskokként, retry-vel.
- [ ] `jobs` tábla bővítése: `user_id`, `job_type`, `params`; a meglévő
      SSE-progress megtartása (a domain-jobs tábla frissül, mint eddig).
- [ ] GraphQL: `myJobs` query, job-cancel mutáció; admin: minden job.
- [ ] Egyidejűség: worker konkurencia = 1 induláskor (a torch-inferencia úgyis
      soros); a queue-séma többet is kibír később.
- **Elfogadás:** API-restart közben futó job túléli és befejeződik; a job a
  userhez kötve listázható; hibás task retry-ol.

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
