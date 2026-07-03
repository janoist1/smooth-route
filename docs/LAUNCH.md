# Publikálási csomag — név, szövegek, elhelyezés, checklist

*Készült: 2026-07-03. A szövegek a „Simaút" névvel íródtak — ha másik név nyer,
csak cserélni kell.*

---

## 1. Névjavaslatok

A „Kátyúőr" problémája: a kátyúra (negatívum) fókuszál, és az „-őr" végződés
hatóságiasan hangzik. Jobb a pozitív ígéretet eladni: a **sima utat**.

| Név | Miért jó | Domain (gyorsellenőrzés) |
|---|---|---|
| **Simaút** ⭐ | Azonnal érthető, rövid, pozitív. Ráadásul a repo neve már most `smooth-route` — a név magától adódott. | `simaut.hu` — szabadnak tűnik ✅ |
| **Zötty** | Játékos, kabalafigura-potenciál („kerüld el a zöttyöket"). Merészebb, de nagyon megjegyezhető. | `zotty.hu` — szabadnak tűnik ✅ |
| **Gördül** | Ige, lendületes; a „gördülékeny" asszociáció autósnak-biciklisnek egyaránt ül. | `gordul.hu` — szabadnak tűnik ✅ |
| **Útradar** | Techesebb: az AI „végigpásztázza" az utakat. Jól magyarázza önmagát. | `utradar.hu` — szabadnak tűnik ✅ |
| **Zökkenőmentes** | Beszédes és vicces kettős jelentés (zökkenő = úthiba és fennakadás), de hosszú. | `zokkeno.hu` — szabadnak tűnik ✅ |

*Megnéztem még: `selyemut.hu` (Selyemút szójáték) — foglalt.*

> **Fontos:** a domain-státusz DNS-alapú gyorsellenőrzés (2026-07-03), nem
> hivatalos — regisztráció előtt a [domain.hu](https://www.domain.hu) keresőben
> kell véglegesíteni. A .hu mellé érdemes lehet a `.app` változatot is megfogni.

**Ajánlás: Simaút.** Egy szó, egy ígéret, és a márka minden szövege
természetesen épül rá („tervezz simán", „a legsimább út"). A Zötty a merész
alternatíva, ha karakteresebb brandet szeretnél.

---

## 2. Szövegek

### Tagline-változatok

1. **Nem a legrövidebb út. A legsimább.**
2. Tudjuk, hol ráz.
3. A kátyúkat mi nézzük, hogy neked ne kelljen.

### Hero (nyitó üzenet)

> **Nem a legrövidebb út. A legsimább.**
>
> A Simaút mesterséges intelligenciával pontozza a magyar utak állapotát,
> és megmutatja, merre gördülhetsz zökkenők nélkül. Kíméld a felnit,
> a derekad és az idegeidet.
>
> [Mutasd a térképet]

### Mi ez? (rövid bemutatkozás)

> A Simaút egy útminőség-térkép és útvonaltervező. Utcaképfelvételek ezreit
> elemezzük mesterséges intelligenciával: a gép minden útszakaszra osztályzatot
> ad egy négyfokú skálán — a frissen aszfaltozott simaságtól a „inkább kerüld
> el" kategóriáig. Az eredményt színezve látod a térképen, útvonaltervezéskor
> pedig nemcsak azt tudod meg, merre visz az út, hanem azt is, milyen állapotban
> vár.

### Hogyan működik? (3 lépés)

> **1. Képek.** Utcaképfelvételeket gyűjtünk az utakról — pontonként, hellyel
> és iránnyal együtt.
>
> **2. Osztályzás.** Egy látás-AI (DINOv2 alapú modell) minden képre
> útminőség-pontszámot ad 1-től (kiváló) 4-ig (rossz). Tízből nyolcszor
> pontosan eltalálja az osztályzatot, és gyakorlatilag sosem téved nagyot —
> az esetek 99,8%-ában legfeljebb egy jegyet.
>
> **3. Térkép.** A pontszámok színezve kerülnek a térképre: zöld = sima,
> sárga = döcögős, piros = kapaszkodj. Útvonaltervezésnél az útvonalad mentén
> is végigelemezzük az utat.

### Célunk

> Az útminőségről ma leginkább akkor értesülsz, amikor már belehajtottál.
> Mi ezen szeretnénk változtatni: őszinte, adatalapú, mindenki számára
> ingyenesen elérhető minőségtérképet építünk Magyarország útjairól.
> Hosszabb távon azt szeretnénk, hogy az útvonalterveződ ne csak a távolságot
> és az időt ismerje, hanem azt is, mit érez majd a lengéscsillapítód —
> és hogy az adataink akár a hibás szakaszok javítását is segítsék.

### Rövid használati útmutató

> **1. Nyisd meg a térképet.** Úgy működik, ahogy megszoktad: húzd, nagyíts,
> nézelődj. A színezett szakaszok a már elemzett utak — a jelmagyarázat a
> térkép sarkában van.
>
> **2. Tervezz útvonalat.** Az útvonaltervező panelen írd be az indulást és
> a célt (pl. „Budapest, Hősök tere"), vagy bökj a térképre a kijelölő
> gombbal.
>
> **3. Elemeztesd az utat.** Az „Elemzés" gombbal az útvonalad menti
> szakaszokat az AI végigpontozza — ez pár percig tarthat, a folyamatot
> a panelen követheted.
>
> **4. Nézz a részletek mögé.** Kattints bármelyik pontra: megkapod a
> helyszín fotóját, a pontszámát, és azt is, milyen hibákat talált rajta
> a gép.

### Mini-FAQ

> **Honnan vannak az adatok?**
> Utcaképfelvételekből, amelyeket mesterséges intelligencia elemez. A modellt
> csaknem kétezer kézzel osztályozott magyar útfotón tanítottuk.
>
> **Mennyire pontos?**
> A négyfokú skálán az esetek ~81%-ában telibe találja az osztályzatot, és
> 99,8%-ban legfeljebb egyet téved. A „jó út vagy rossz út?" kérdésre 92%-ban
> jól válaszol. Tévedni azért tud — a fotó alapján dolgozik, ahogy te is tennéd.
>
> **Mennyire friss?**
> Annyira, amennyire a felvétel, amiből dolgozunk — a részletkártyán mindig
> látod a forrásképet. Ha időközben megjavították az utat: örülünk, és
> hamarosan mi is frissítünk.
>
> **Ingyenes?**
> Igen. Regisztrációval tudsz saját elemzéseket indítani — méltányos napi
> kerettel, hogy a szerverünk is sima maradjon.
>
> **Miért nincs adat az én utcámról?**
> Mert még nem járt arra az elemzés. Tervezz rá útvonalat, és pótoljuk!

### Első látogatáskor felugró üdvözlő (welcome-kártya)

> **Szia! Ez itt a Simaút.** 👋
>
> Térkép, ami tudja, hol ráz az út.
>
> 🗺️ A színek az út állapotát mutatják: zöld = sima, piros = döcög.
> 🔍 Tervezz útvonalat, és az AI végigpontozza az utat.
> 📸 Bökj egy pontra, és megnézheted, mit látott a gép.
>
> [Vágjunk bele]

---

## 3. Hova kerüljenek a szövegek? (térkép-first UX)

A Google Maps-jellegű apphoz **nem kell külön nyitóképernyő** — a térkép maga
a legjobb belépő. Javasolt elrendezés:

1. **Welcome-kártya első látogatáskor** — a fenti üdvözlő szöveg kis kártyán
   a térkép fölött, egyszer jelenik meg (`localStorage` flag), „Vágjunk bele"
   gombbal zárható. Nem modális teljes képernyő — hadd látsszon mögötte a
   térkép, az az igazi hook.
2. **ℹ️ „Névjegy" a meglévő FloatingNav-ban** — oldalpanel vagy popup a
   „Mi ez?", „Hogyan működik?", „Célunk" és FAQ szekciókkal. Ide bármikor
   vissza lehet térni, ez a súgó is egyben.
3. **`/rolunk` statikus aloldal** — ugyanez a tartalom külön URL-en. Ez kell
   a SEO-hoz (a térkép-app önmagában nem indexelhető jól) és ahhoz, hogy
   legyen megosztható link, ami elmagyarázza a projektet.
4. **Lábléc-linkek a panelben/aloldalon** — Adatkezelési tájékoztató,
   Impresszum, Kapcsolat.
5. **Üres állapot** — ahol még nincs adat, egy rövid tooltip magyarázza:
   „Itt még nem járt az elemzés — tervezz útvonalat, és pótoljuk."

---

## 4. Mi kell még a publikáláshoz?

A [PUBLISH_PLAN.md](PUBLISH_PLAN.md) (auth, kvóták, infra, F0–F6) mellett:

### Kirakat

- [ ] **`frontend/index.html`**: a `<title>` most „frontend" — cserélni a
  végleges névre + `meta description` + Open Graph tagek (og:title, og:image
  — egy szép színezett térkép-screenshot) + favicon/logó.
- [ ] **Logó**: egyszerű, térképen is működő jel (pl. hullámvonal-mentes út
  ikon). A Zötty névhez kabalafigura is elférne.
- [ ] **Domain**: a választott nevet regisztrálni (domain.hu), a PUBLISH_PLAN
  már számol ~1 €/hó domainköltséggel.

### Jog (publikálás előtt kötelező)

- [ ] **Adatkezelési tájékoztató** — GDPR: Clerk-regisztráció (e-mail),
  analytics, szerver-logok.
- [ ] **Impresszum** — magyar oldalnál elvárt (üzemeltető, elérhetőség).
- [ ] **Süti/consent** — ha csak Clerk + privacy-barát analytics fut,
  minimális, de tisztázni kell.
- [ ] **Google Maps Platform ToS** — a Street View képek megjelenítéséhez
  Google-attribúció kötelező a képeken; a származtatott adatok (pontszámok)
  tárolási/megjelenítési szabályait érdemes átnézni publikálás előtt.

### Működés

- [ ] **Analytics** — privacy-barát (Plausible/Umami), consent-teher nélkül.
- [ ] **Visszajelzés-csatorna** — legalább egy „Hibát találtál? Írj!" mailto
  vagy űrlap a Névjegy panelen. Az első felhasználók aranyat érő hibákat
  találnak.
- [ ] **SEO-alap** — sitemap.xml, robots.txt, canonical a `/rolunk` oldalra.

### Bemutatás (ha élesben van)

- [ ] Magyar autós/biciklis Facebook-csoportok, r/hungary, prog.hu / HUP
  (tech sztori: „AI pontozza a magyar utakat" — a MODEL_EXPERIMENTS.md
  történetéből jó poszt írható).
- [ ] Tech-sajtó tipp (Telex/444/hvg tech): a „gép osztályozza a kátyúkat"
  vizuális sztori, screenshotokkal jól eladható.
