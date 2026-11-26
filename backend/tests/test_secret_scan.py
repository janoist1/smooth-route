"""publish.py's last-line check: no credential leaves for Neon."""
from app.core.secret_scan import find_secrets

FAKE_KEY = "AIza" + "x" * 35  # shape only, not a real key


def test_finds_google_key_in_url_and_json():
    rows = [
        {"id": 1, "image_url": f"https://maps.googleapis.com/maps/api/streetview?size=640x640&key={FAKE_KEY}"},
        {"id": 2, "analysis_metadata": {"src": f"x?key={FAKE_KEY}"}},
        {"id": 3, "image_url": None, "rqi_score": 2.0, "pano_id": "CAoSLEFGMVFpcE"},
    ]
    hits = find_secrets(rows)
    assert {(h[0], h[1]) for h in hits} == {(1, "image_url"), (2, "analysis_metadata")}
    assert all(FAKE_KEY not in str(h) for h in hits)  # locations only


def test_clean_public_rows_pass():
    rows = [{"id": 7, "image_url": None, "street": "Andrássy út", "damage_types": {"pothole": 1},
             "geom": "LINESTRING(19 47, 19.1 47.1)", "capture_date": "2021-07-01"}]
    assert find_secrets(rows) == []


def test_db_url_with_password_flagged():
    assert find_secrets([{"id": 1, "note": "postgresql://u:hunter2@ep-x.neon.tech/db"}])
