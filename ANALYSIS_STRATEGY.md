# RQI Algoritmus Finomhangolási Stratégia

## Jelenlegi Helyzet

### Probléma
Az algoritmus túl rosszul minősíti az utakat - a legtöbb út RQI 4-5-öt kap, ami túl rossz.

### Adatok
- **Átlagos damage_score**: 20.54
- **Medián damage_score**: 21.68
- **75% kvantilis**: 26.65
- **RQI eloszlás**: 
  - RQI 1: 73 pont (6.6%)
  - RQI 2: 1 pont (0.1%)
  - RQI 3: 112 pont (10.2%)
  - RQI 4: 556 pont (50.6%)
  - RQI 5: 356 pont (32.4%)

### Jelenlegi Küszöbértékek
- RQI 1 (Excellent): damage_score < 2
- RQI 2 (Good): damage_score < 5
- RQI 3 (Fair): damage_score < 12
- RQI 4 (Poor): damage_score < 25
- RQI 5 (Very Poor): damage_score >= 25

## Lehetőségek

### 1. **Kvantilis-alapú Normalizálás** ⭐ AJÁNLOTT
**Előnyök:**
- Automatikusan alkalmazkodik az adatokhoz
- Nem kell manuális kalibrálás
- Robusztus a kiugró értékekre

**Megközelítés:**
- Használjuk a damage_score eloszlását
- RQI 1: < 25% kvantilis
- RQI 2: 25-50% kvantilis
- RQI 3: 50-75% kvantilis
- RQI 4: 75-90% kvantilis
- RQI 5: > 90% kvantilis

**Implementáció:**
```python
# Számítsuk ki a kvantiliseket egy reprezentatív mintán
quantiles = np.percentile(damage_scores, [25, 50, 75, 90])
if damage_score < quantiles[0]:
    rqi = 1.0
elif damage_score < quantiles[1]:
    rqi = 2.0
elif damage_score < quantiles[2]:
    rqi = 3.0
elif damage_score < quantiles[3]:
    rqi = 4.0
else:
    rqi = 5.0
```

### 2. **Machine Learning Modell Használata**
**Előnyök:**
- Pontosabb, mint a heurisztika
- Tanul a valós adatokból
- Kevesebb false positive

**Hátrányok:**
- Szükség van címkézett adatokra
- Lassabb, mint a heurisztika
- Nehezebb debugolni

**Megközelítés:**
- Használjuk a YOLO modellt (már implementálva van)
- Vagy finomhangoljuk egy road damage dataset-en

### 3. **Ensemble Módszer**
**Előnyök:**
- Kombinálja a heurisztika és ML előnyeit
- Robusztusabb
- Jobb teljesítmény

**Megközelítés:**
- Kombináljuk a `analyze_image_simple` és `analyze_image` eredményeit
- Súlyozott átlag vagy voting

### 4. **Manuális Kalibrálás Referencia Képekkel**
**Előnyök:**
- Pontos, ha jó referenciákat használunk
- Kontrollálható

**Hátrányok:**
- Időigényes
- Szubjektív
- Nehezen skálázható

**Megközelítés:**
1. Válasszunk ki 20-30 képet (5-6 minden RQI szintről)
2. Manuálisan címkézzük őket
3. Finomhangoljuk a küszöbértékeket, hogy illeszkedjenek

### 5. **Algoritmus Finomhangolása**
**Előnyök:**
- Gyors
- Könnyen implementálható
- Jó, ha a metrikák jók

**Hátrányok:**
- Találgatás lehet
- Nehezen skálázható

**Megközelítés:**
- Csökkentsük a súlyokat
- Módosítsuk a küszöbértékeket
- Finomhangoljuk a Canny/HoughLinesP paramétereket

## Ajánlott Megközelítés

### Fázis 1: Kvantilis-alapú Normalizálás (Rövid táv)
1. Számítsuk ki a kvantiliseket az összes pont damage_score-jából
2. Használjuk ezeket a küszöbértékekként
3. Teszteljük és értékeljük

### Fázis 2: Algoritmus Finomhangolása (Közép táv)
1. Elemezzük, mely metrikák okozzák a magas damage_score-ot
2. Finomhangoljuk a súlyokat és paramétereket
3. Kombináljuk a kvantilis-alapú normalizálással

### Fázis 3: ML Modell Integrációja (Hosszú táv)
1. Használjuk a YOLO modellt a valós károsodások detektálására
2. Kombináljuk a heurisztikával ensemble módszerrel
3. Finomhangoljuk címkézett adatokkal

## Következő Lépések

1. ✅ Adatok elemzése - megértjük mi történik
2. ⏭️ Kvantilis-alapú normalizálás implementálása
3. ⏭️ Tesztelés és értékelés
4. ⏭️ Finomhangolás visszajelzések alapján

