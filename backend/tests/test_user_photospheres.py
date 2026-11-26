"""User-contributed photospheres are not road-level Street View: the collector
skips them after the free metadata call, and the client asks for outdoor
panoramas. No network: HTTP and Google are faked."""
import json

import pytest

from app.services.sv_client import StreetViewClient, is_google_pano
from app.services.sv_quota import StreetViewQuota
from test_network_collection import ROAD, FakeGoogle, FakeStore, one, sample_line


@pytest.mark.parametrize("meta,own", [
    ({"pano_id": "tvzdjPn_sOId2TDOAp2Uzw", "copyright": "© 2026 Google"}, True),
    ({"pano_id": "CAoSF0NJSE0wb2dLRUlDQWdJ", "copyright": "© István Sulyok"}, False),
    ({"pano_id": "tvzdjPn_sOId2TDOAp2Uzw", "copyright": "© Someone"}, False),
    ({"pano_id": "CAoSF0NJSE0wb2dLRUlDQWdJ"}, False),   # no copyright: id pattern decides
    ({"pano_id": "tvzdjPn_sOId2TDOAp2Uzw"}, True),
    (None, False),
])
def test_is_google_pano(meta, own):
    assert is_google_pano(meta) is own


def test_collector_skips_a_user_photosphere_without_buying_the_image(tmp_path, monkeypatch):
    google = FakeGoogle(tmp_path)
    real = google.metadata

    def user_meta(*a, **kw):
        return {**real(*a, **kw), "copyright": "© A Person"}

    monkeypatch.setattr(google, "metadata", user_meta)
    candidate = sample_line(ROAD, 50)[3]
    assert one(candidate, google, FakeStore()) == ("user_pano", None, 0)
    assert google.image_calls == [] and google.quota.used() == 0


def test_client_asks_for_outdoor_panoramas_and_returns_the_copyright(tmp_path):
    sent = []

    def http(url, params, timeout_s):
        sent.append(params)
        body = {"status": "OK", "pano_id": "p1", "location": {"lat": 47.5, "lng": 19.0},
                "date": "2025-09", "copyright": "© 2026 Google"}
        return 200, "application/json", json.dumps(body).encode()

    c = StreetViewClient("K", StreetViewQuota(tmp_path / "q.json", monthly_cap=5),
                         http_get=http, sleep=lambda s: None)
    meta = c.metadata(47.5, 19.0, radius=25)
    assert meta["copyright"] == "© 2026 Google"
    assert sent[0]["source"] == "outdoor"
    c.metadata(pano_id="p1")
    assert "source" not in sent[1]  # a pano-id lookup needs no filter


def test_marking_keeps_other_frame_quality_fields_and_is_idempotent():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).parents[1] / "scripts" / "mark_user_photospheres.py"
    spec = importlib.util.spec_from_file_location("mark_user_photospheres", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    old = {"dino_score": 2.1, "frame_quality": {"usable": False, "reasons": ["hood"], "blur": 9.0}}
    new = mod.mark(old)
    assert new["frame_quality"] == {"usable": False, "reasons": ["hood", "user_photosphere"], "blur": 9.0}
    assert new["dino_score"] == 2.1 and old["frame_quality"]["reasons"] == ["hood"]  # input untouched
    assert mod.mark(new) == new and mod.already_marked(new)
    assert mod.mark(None)["frame_quality"] == {"usable": False, "reasons": ["user_photosphere"]}
    assert not mod.already_marked({"frame_quality": {"usable": True}})
