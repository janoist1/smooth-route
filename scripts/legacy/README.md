# scripts/legacy — régi, egyszeri diagnosztika (nem karbantartott)

A YOLO-korszak (v2 RQI-modell előtti) egyszeri kalibrációs/diagnosztikai
szkriptjei. **Nem részei a workflow-nak**, nem hivatkozik rájuk a `Makefile`, és
nincs garancia, hogy a jelenlegi kóddal futnak (pl. a `verify_real_images.py`
a már nem létező `analyze_image_simple`-t hívja). Referenciának maradtak; a
repó gyökeréből futtatandók (`sys.path`-hoz a `backend/`-et a cwd-ből adják).

Az élő karbantartó szkriptek eggyel feljebb, a `scripts/`-ben vannak
(`clear_jobs.py`, `list_jobs.py` → `make clear-jobs` / `make list-jobs`).
