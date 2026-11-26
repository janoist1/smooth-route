# Launch kit — name, copy, placement, checklist

Product copy is Hungarian (it ships in the UI); everything around it is English.
Written 2026-07-03, accuracy claims updated 2026-11-26 to the spatial-CV numbers
([ml/README.md](../ml/README.md)). Nothing here is implemented yet: `frontend/index.html`
still has `<title>frontend</title>`, and there is no welcome card or `/rolunk` page.

## 1. Name

"Kátyúőr" sells the negative (potholes) and "-őr" sounds official. Sell the promise
instead: the smooth road. **Chosen working name: Simaút** (`simaut.hu`; the repo is
already `smooth-route`; the deploy plan assumes `simaut.hu` / `api.simaut.hu`).
Alternatives considered: Zötty (playful, mascot potential), Gördül, Útradar,
Zökkenőmentes; `selyemut.hu` was taken. Domain availability was a DNS check on
2026-07-03 — confirm at domain.hu before registering.

## 2. Copy (Hungarian)

Rules for any copy: accuracy claims must match the **current** official numbers;
features marked *(round 2)* are not on the read-only public site — leave them out
until round 2 ships.

**Tagline options:** „Nem a legrövidebb út. A legsimább." · „Tudjuk, hol ráz." ·
„A kátyúkat mi nézzük, hogy neked ne kelljen."

**Hero**
> **Nem a legrövidebb út. A legsimább.**
> A Simaút mesterséges intelligenciával pontozza a magyar utak állapotát, és
> megmutatja, merre gördülhetsz zökkenők nélkül. Kíméld a felnit, a derekad és az
> idegeidet. [Mutasd a térképet]

**Mi ez?**
> A Simaút útminőség-térkép. Utcaképfelvételek ezreit elemezzük mesterséges
> intelligenciával: a gép minden pontra osztályzatot ad egy négyfokú skálán — a
> frissen aszfaltozott simaságtól az „inkább kerüld el" kategóriáig. Az eredményt
> színezve látod a térképen.

**Hogyan működik? (3 lépés)**
> **1. Képek.** Utcaképfelvételeket gyűjtünk az utakról — pontonként, hellyel és
> iránnyal.
> **2. Osztályzás.** Egy látás-AI (DINOv2 alapú modell) minden képre 1-től (kiváló)
> 4-ig (rossz) ad pontszámot. Sosem látott utcákon tízből hatszor pontosan
> eltalálja az osztályzatot, és szinte mindig legfeljebb egyet téved; a „jó vagy
> rossz az út?" kérdésben megbízható.
> **3. Térkép.** Zöld = sima, sárga = döcögős, piros = kapaszkodj.

**Célunk**
> Az útminőségről ma leginkább akkor értesülsz, amikor már belehajtottál. Őszinte,
> adatalapú, ingyenes minőségtérképet építünk Magyarország útjairól — hosszabb
> távon olyat, amit az útvonaltervező is figyelembe vesz, és ami a hibás szakaszok
> javítását is segítheti.

**Rövid használati útmutató**
> **1. Nyisd meg a térképet.** Húzd, nagyíts, nézelődj; a színezett részek a már
> elemzett utak, a jelmagyarázat a sarokban.
> **2. Nézz a részletek mögé.** Kattints egy pontra: látod a pontszámát, a rossz út
> valószínűségét, a felvétel dátumát, és megnyithatod a helyszínt Street View-ban.
> **3. Tervezz útvonalat** *(round 2)*: az útvonaltervezőben megadod az indulást és
> a célt, az „Elemzés" gombbal az AI végigpontozza az utat.

**Mini-FAQ**
> **Honnan vannak az adatok?** Utcaképfelvételekből, amelyeket mesterséges
> intelligencia elemez; a modellt csaknem kétezer kézzel osztályozott magyar
> útfotón tanítottuk.
> **Mennyire pontos?** Sosem látott utcákon az esetek ~60%-ában pontosan eltalálja
> az osztályzatot, és 98,5%-ban legfeljebb egyet téved. A jó/rossz utat megbízhatóan
> megkülönbözteti; Budapesten egyelőre gyengébb, ott még gyűjtünk adatot.
> **Mennyire friss?** Annyira, amennyire a felvétel — a részletkártyán látod a
> felvétel hónapját, és szólunk, ha a kép régi.
> **Ingyenes?** Igen. *(round 2: regisztrációval saját elemzést is indíthatsz,
> méltányos napi kerettel.)*
> **Miért nincs adat az én utcámról?** Mert még nem járt arra az elemzés.

**Welcome card (first visit)**
> **Szia! Ez itt a Simaút.** Térkép, ami tudja, hol ráz az út.
> A színek az út állapotát mutatják: zöld = sima, piros = döcög. Bökj egy pontra,
> és megnézheted, mit látott a gép. [Vágjunk bele]

## 3. Placement (map-first UX)

No separate landing screen — the map is the hook.

1. **Welcome card** on first visit over the map, dismissible, `localStorage` flag; not
   a full-screen modal.
2. **"Névjegy" (ℹ️) in FloatingNav** — panel with Mi ez? / Hogyan működik? / Célunk / FAQ.
3. **`/rolunk` static page** with the same content — needed for SEO and a shareable link.
4. **Footer links** in the panel/page: privacy notice, impresszum, contact.
5. **Empty state** tooltip where there is no data yet.

## 4. Launch checklist (besides [PUBLISH_PLAN.md](PUBLISH_PLAN.md))

**Storefront**
- [ ] `frontend/index.html`: real `<title>`, meta description, Open Graph tags
  (og:image = a coloured map screenshot), favicon/logo.
- [ ] Logo that works on a map.
- [ ] Domain registered (part of R1.4).

**Legal (required before launch)**
- [ ] Privacy notice (GDPR: server logs, analytics; Clerk e-mail only in round 2).
- [ ] Impresszum (operator, contact).
- [ ] Cookie/consent — minimal if only privacy-friendly analytics runs.
- [ ] Google Maps Platform ToS review: attribution, rules for derived data (scores).

**Operations**
- [ ] Privacy-friendly analytics (Plausible/Umami).
- [ ] Feedback channel ("Hibát találtál? Írj!" mailto or form in Névjegy).
- [ ] SEO basics: sitemap.xml, robots.txt, canonical on `/rolunk`.

**Announcement (once live):** Hungarian driver/cyclist Facebook groups, r/hungary,
prog.hu / HUP (the "AI grades Hungarian roads" story), tech press tips
(Telex/444/hvg) with screenshots.
