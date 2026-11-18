# RQI Algoritmus Javítási Stratégia

## Probléma
A jelenlegi heurisztikus algoritmus túl rosszul minősíti az utakat - jó utakat rossznak lát. A probléma:
- Normál útburkolat textúráját károsodásnak értelmezi
- Útvonaljelölések, árnyékok zavarhatják
- Nem elég specifikus a valós károsodásokra

## Lehetőségek

### 1. **Ensemble Módszer** ⭐ LEGJOBB
**Előnyök:**
- Kombinálja a heurisztika és ML előnyeit
- Robusztusabb, kevesebb false positive
- Használhatjuk a már implementált YOLO-t

**Megközelítés:**
```python
def analyze_image_ensemble(image_path):
    # 1. Heurisztikus elemzés
    heuristic_result = analyze_image_simple(image_path)
    
    # 2. YOLO elemzés (ha van modell)
    yolo_result = analyze_image(image_path)
    
    # 3. Kombinálás súlyozott átlaggal vagy voting-gal
    # Ha YOLO talál károsodást -> rosszabb RQI
    # Ha YOLO nem talál -> heurisztika alapján, de konzervatívabban
    if yolo_result.damage_count > 0:
        # YOLO talált károsodást -> használjuk
        final_rqi = yolo_result.rqi_score
    else:
        # Nincs YOLO detektálás -> heurisztika, de konzervatívabban
        # Csak akkor rossz, ha tényleg magas a damage_score
        if heuristic_result.damage_score > 30:  # Magas küszöb
            final_rqi = min(heuristic_result.rqi_score + 1, 5.0)  # Rosszabbítunk
        else:
            final_rqi = max(heuristic_result.rqi_score - 0.5, 1.0)  # Javítunk
```

### 2. **Jobb Heurisztika: Útburkolat vs Károsodás Különbségtétel**
**Probléma:** A jelenlegi algoritmus nem különbözteti meg jól a normál útburkolat textúráját a károsodástól.

**Megoldás:**
- **Útvonaljelölés szűrés**: Fehér/sárga vonalak kizárása
- **Strukturális elemzés**: Csak hosszú, egyenes vonalak (repedések), nem véletlenszerű textúra
- **Kontraszt analízis**: Károsodásoknak magasabb kontrasztuk van, mint a normál textúrának
- **Blokkok közötti variancia**: Károsodások lokálisak, nem egyenletesen elosztottak

**Implementáció:**
```python
# 1. Útvonaljelölés detektálás és kizárás
white_mask = cv2.inRange(road_region, (200, 200, 200), (255, 255, 255))
yellow_mask = cv2.inRange(road_region, (0, 200, 200), (100, 255, 255))
markings_mask = white_mask | yellow_mask

# 2. Csak nem-jelöléses területeken számolunk damage_score-t
road_without_markings = cv2.bitwise_and(gray, cv2.bitwise_not(markings_mask))

# 3. Strukturális elemzés: csak hosszú vonalak (repedések)
# HoughLinesP csak akkor számít, ha a vonalak hosszúak és egyenesek
lines = cv2.HoughLinesP(edges_fine, 1, np.pi/180, threshold=50, 
                        minLineLength=50, maxLineGap=5)  # Hosszabb vonalak

# 4. Blokkok közötti variancia: károsodások lokálisak
# Ha a variancia egyenletesen elosztott -> normál textúra
# Ha lokális csúcsok vannak -> károsodás
block_variances = [np.var(block) for block in blocks]
variance_std = np.std(block_variances)
# Magas std -> lokális károsodások
# Alacsony std -> egyenletes textúra (normál út)
```

### 3. **Referencia Alapú Kalibrálás**
**Megközelítés:**
- Használjunk referencia képeket (jó/rossz utak)
- Számítsuk ki a damage_score-okat ezekre
- Állítsuk be a küszöbértékeket, hogy illeszkedjenek

### 4. **YOLO Finomhangolás Road Damage Dataset-en**
**Előnyök:**
- Legpontosabb megoldás
- Tanul a valós károsodásokról

**Hátrányok:**
- Szükség van címkézett adatokra
- Lassabb feldolgozás
- Modell betanítása szükséges

**Megközelítés:**
- Használjuk az RDD2020 dataset-et (Road Damage Dataset)
- Finomhangoljuk a YOLOv8-t ezen az adathalmazon
- Integráljuk a rendszerbe

### 5. **Kombinált Megközelítés: Többlépcsős Szűrés**
**Stratégia:**
1. **Első szűrés**: YOLO detektálás - ha talál károsodást, az biztos
2. **Második szűrés**: Heurisztika csak akkor, ha YOLO nem talált semmit
3. **Konzervatív küszöbök**: Csak akkor rossz, ha tényleg magas a damage_score

## Ajánlott Megközelítés

### Rövid táv (azonnali javítás):
1. **Útvonaljelölés szűrés**: Fehér/sárga vonalak kizárása a damage_score számításból
2. **Konzervatívabb küszöbök**: Csak akkor rossz, ha damage_score > 30-35
3. **Strukturális elemzés javítása**: Csak hosszú, egyenes vonalak számítanak (repedések)

### Közép táv:
1. **Ensemble módszer**: Kombináljuk a heurisztikát és YOLO-t
2. **Jobb blokk variancia analízis**: Lokális vs globális textúra különbségtétel

### Hosszú táv:
1. **YOLO finomhangolás**: Road Damage Dataset-en
2. **Referencia alapú kalibrálás**: Manuálisan címkézett képek

## Implementációs Prioritás

1. **1. lépés**: Útvonaljelölés szűrés + konzervatívabb küszöbök
2. **2. lépés**: Ensemble módszer (YOLO + heurisztika)
3. **3. lépés**: Strukturális elemzés javítása
4. **4. lépés**: YOLO finomhangolás (ha szükséges)

