"""Pairwise mode: pair picking (pure) and the Bradley-Terry fit (ml/, numpy only)."""
import importlib.util
import math
import pathlib

import pytest

from app.services import label_queue as lq
from app.services.label_queue import Frame


def at(dx_m, base=(47.4981, 19.0713)):
    return base[0], base[1] + dx_m / (lq.M_PER_DEG * math.cos(math.radians(lq.LAT_REF)))


def f(fid, score, dx):
    lat, lon = at(dx)
    return Frame(id=fid, lat=lat, lon=lon, score=score)


class TestPickPairs:
    def test_close_scores_far_apart_each_frame_once(self):
        frames = [f(1, 2.00, 0), f(2, 2.10, 1000), f(3, 2.15, 2000), f(4, 2.20, 3000),
                  f(5, 3.50, 4000)]
        pairs = lq.pick_pairs(frames, 10)
        ids = [x.id for a, b, _ in pairs for x in (a, b)]
        assert len(ids) == len(set(ids))                     # each frame once
        assert all(gap <= lq.PAIR_MAX_GAP for *_, gap in pairs)
        assert 5 not in ids                                   # nothing close to 3.5

    def test_too_close_in_space_and_already_judged_are_skipped(self):
        frames = [f(1, 2.0, 0), f(2, 2.05, 100), f(3, 2.1, 1000)]
        assert all({a.id, b.id} != {1, 2} for a, b, _ in lq.pick_pairs(frames, 5))  # 100 m apart
        assert lq.pick_pairs([f(1, 2.0, 0), f(3, 2.1, 1000)], 5, judged=[(3, 1)]) == []

    def test_unscored_and_excluded_frames_never_pair(self):
        frames = [f(1, None, 0), f(2, 2.0, 1000), f(3, 2.1, 2000)]
        assert lq.pick_pairs(frames, 5, exclude_ids=[3]) == []


def _ml():
    path = pathlib.Path(__file__).parents[2] / "ml" / "pairwise_scores.py"
    spec = importlib.util.spec_from_file_location("pairwise_scores", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bradley_terry_orders_frames_by_the_judgments():
    fit = _ml().fit_scores
    # 0 < 1 < 2 in badness, judged repeatedly; no priors.
    pairs = [(1, 0, 1.0), (2, 1, 1.0), (2, 0, 1.0)] * 5
    s = fit(3, pairs, {})
    assert s[0] < s[1] < s[2]


def test_labels_anchor_the_scale_and_pairs_place_the_rest():
    fit = _ml().fit_scores
    priors = {0: (1.0, 1.0), 1: (4.0, 1.0)}           # labelled best / worst
    pairs = [(2, 0, 1.0), (1, 2, 1.0)] * 3             # frame 2 sits in between
    s = fit(3, pairs, priors)
    assert s[0] < s[2] < s[1]
    assert s[0] == pytest.approx(1.0, abs=0.6) and s[1] == pytest.approx(4.0, abs=0.6)
    equal = fit(2, [(0, 1, 0.5)] * 4, {0: (2.0, 1.0), 1: (2.0, 1.0)})
    assert equal[0] == pytest.approx(equal[1])


def test_sprint_mixes_new_streets_with_model_best_and_keeps_75m_apart():
    frames = [f(i, 1.0 + (i % 30) / 10, i * 40) for i in range(1, 400)]  # 40 m spacing
    res = lq.build_queue(frames, [], "sprint", 12)
    reasons = [it.reason for it in res.items]
    assert reasons[:4] == ["diverse", "diverse", "diverse", "model_best"]
    pts = [lq.to_xy(it.frame.lat, it.frame.lon) for it in res.items if it.reason == "diverse"]
    assert all(math.hypot(a[0] - b[0], a[1] - b[1]) >= lq.SPRINT_THIN_M
               for i, a in enumerate(pts) for b in pts[i + 1:])
    best = [it.frame.score for it in res.items if it.reason == "model_best"]
    assert best == sorted(best) and best[0] == min(fr.score for fr in frames)


@pytest.mark.parametrize("query", [
    "{ pairQueue { judged } }",
    'mutation { submitPairJudgment(input: {clientId: "x", frameAId: 1, frameBId: 2, result: A}) }',
    'mutation { undoPairJudgment(clientId: "x") }',
])
def test_pairwise_api_is_admin_only(query):
    from app.core.auth import Identity
    from app.graphql.schema import read_schema, schema

    user = Identity(user_id="u", clerk_id="u", email=None, role="user")
    for identity in (None, user):
        res = schema.execute_sync(query, context_value={"identity": identity})
        assert res.data is None and "Admin privileges required" in res.errors[0].message
    assert "pair_queue" not in {fld.python_name for fld in read_schema.get_type_by_name("Query").fields}
