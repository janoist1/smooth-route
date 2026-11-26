"""Pure aggregation helpers of scripts/coverage_report.py (no DB).

Loading the script module here also proves it imports without a database:
SQLAlchemy and the session are only imported inside load() / main().
"""
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

from app.core.rqi_scale import SCALE
from app.services.segment_aggregation import frame_usable

_SPEC = importlib.util.spec_from_file_location(
    "coverage_report", Path(__file__).resolve().parents[1] / "scripts" / "coverage_report.py"
)
cov = importlib.util.module_from_spec(_SPEC)
sys.modules["coverage_report"] = cov  # dataclasses resolve annotations via sys.modules
_SPEC.loader.exec_module(cov)

TODAY = dt.date(2026, 11, 26)
INNER = (47.4981, 19.0713)       # Budapest centroid, inside the inner box
BUDA_NORTH = (47.55, 19.02)
TAPOLCA = (46.8681, 17.3897)
FAR = (47.65, 21.60)             # Debrecen direction: "other"


def frame(pos, **kw):
    return cov.FrameRec(lat=pos[0], lon=pos[1], **kw)


def seg(pos, **kw):
    kw.setdefault("length_m", 200.0)
    kw.setdefault("level", "medium")
    return cov.SegmentRec(lat=pos[0], lon=pos[1], **kw)


def test_share_handles_empty_whole():
    assert cov.share(1, 4) == 0.25
    assert cov.share(3, 0) == 0.0


def test_area_keys_put_budapest_into_a_sector_row():
    assert cov.area_keys(*INNER) == ("budapest", "budapest / inner (V-IX)")
    assert cov.area_keys(*BUDA_NORTH) == ("budapest", "budapest / Buda north (II, III)")
    assert cov.area_keys(*TAPOLCA) == ("tapolca",)
    assert cov.area_keys(*FAR) == ("other",)


def test_every_budapest_position_falls_in_a_named_sector():
    for lat in (47.40, 47.475, 47.50, 47.515, 47.60):
        for lon in (18.95, 19.045, 19.05, 19.095, 19.20):
            assert cov.budapest_sector(lat, lon) != "elsewhere"


def test_row_order_nests_sectors_under_budapest_and_ends_with_total():
    keys = {cov.TOTAL, "other", "budapest / Buda north (II, III)", "tapolca",
            "budapest", "budapest / inner (V-IX)"}
    assert cov.row_order(keys) == [
        "budapest", "budapest / inner (V-IX)", "budapest / Buda north (II, III)",
        "tapolca", "other", cov.TOTAL,
    ]


def test_summarize_counts_frames_per_area_and_total():
    frames = [
        frame(INNER, labelled=True, capture_date=dt.date(2025, 6, 1)),   # 1.5 y
        frame(INNER, usable=False, capture_date=dt.date(2022, 6, 1)),    # 4.5 y
        frame(TAPOLCA, capture_date=dt.date(2019, 6, 1)),                # 7.5 y
        frame(FAR),                                                       # undated
    ]
    stats = cov.summarize(frames, [], TODAY)

    bp = stats["budapest"]
    assert (bp.frames, bp.usable, bp.unusable, bp.labelled) == (2, 1, 1, 1)
    assert (bp.dated, bp.older[3], bp.older[5]) == (2, 1, 0)
    assert stats["budapest / inner (V-IX)"].frames == 2
    assert stats["tapolca"].older == {3: 1, 5: 1}
    assert stats["other"].dated == 0

    total = stats[cov.TOTAL]
    assert (total.frames, total.usable, total.unusable, total.labelled) == (4, 3, 1, 1)
    assert (total.dated, total.older[3], total.older[5]) == (3, 2, 1)


def test_age_boundary_is_strictly_older():
    just_under_three = TODAY - dt.timedelta(days=1095)  # 3 * 365.25 = 1095.75
    stats = cov.summarize([frame(FAR, capture_date=just_under_three)], [], TODAY)
    assert stats["other"].older[3] == 0
    just_over = TODAY - dt.timedelta(days=1096)
    stats = cov.summarize([frame(FAR, capture_date=just_over)], [], TODAY)
    assert stats["other"].older == {3: 1, 5: 0}


def test_summarize_segments_by_class_level_and_unlabelled_area():
    best, worst = SCALE.best, SCALE.worst
    segments = [
        seg(INNER, rqi=best, level="high", length_m=1000.0),
        seg(INNER, rqi=worst, level="low", length_m=500.0, unlabelled_area=True),
        seg(FAR, rqi=None, level="low", length_m=250.0, unlabelled_area=True),
    ]
    stats = cov.summarize([], segments, TODAY)

    bp = stats["budapest"]
    assert bp.segments == 2 and bp.km == pytest.approx(1.5)
    assert bp.km_by_class[best] == pytest.approx(1.0)
    assert bp.segments_by_class[worst] == 1
    assert bp.km_by_level["high"] == pytest.approx(1.0)
    assert bp.unlabelled_segments == 1 and bp.unlabelled_km == pytest.approx(0.5)

    total = stats[cov.TOTAL]
    assert total.segments == 3 and total.km == pytest.approx(1.75)
    assert total.segments_by_class[cov.UNSCORED] == 1
    assert total.unlabelled_km == pytest.approx(0.75)
    assert cov.share(total.unlabelled_km, total.km) == pytest.approx(0.75 / 1.75)
    # best -> worst on the canonical scale, unscored last
    assert cov.class_columns(stats) == [best, worst, cov.UNSCORED]


def test_cell_of_is_about_one_km_and_centre_round_trips():
    cell = cov.cell_of(*INNER)
    lat, lon = cov.cell_centre(cell)
    assert cov.cell_of(lat, lon) == cell
    assert cov.haversine_km(INNER[0], INNER[1], lat, lon) < 0.75  # half a diagonal
    north = cov.cell_centre((cell[0] + 1, cell[1]))
    east = cov.cell_centre((cell[0], cell[1] + 1))
    assert cov.haversine_km(lat, lon, *north) == pytest.approx(1.0, abs=0.02)
    assert cov.haversine_km(lat, lon, *east) == pytest.approx(1.0, abs=0.02)
    assert cov.cell_of(*INNER, cell_km=5.0) != cell


def test_unlabelled_cells_rank_by_usable_frames_and_skip_labelled_cells():
    frames = (
        [frame(BUDA_NORTH)] * 3
        + [frame(BUDA_NORTH, usable=False)] * 10            # unusable frames do not count
        + [frame(FAR)] * 5
        + [frame(INNER)] * 9 + [frame(INNER, labelled=True)]  # a labelled frame rules its cell out
        + [frame(TAPOLCA)] * 7                               # ruled out by a legacy label position
    )
    cells = cov.unlabelled_cells(frames, labelled_points=[TAPOLCA], top=20)

    assert [(c.area, c.frames) for c in cells] == [
        ("other", 5), ("budapest / Buda north (II, III)", 3)]
    assert cells[0].nearest_label_km > 100
    assert cov.unlabelled_cells(frames, [TAPOLCA], top=1)[0].frames == 5
    assert cov.unlabelled_cells(frames, [], top=0) == []


def test_unlabelled_cells_without_any_label_have_no_distance():
    (cell,) = cov.unlabelled_cells([frame(FAR)], [], top=5)
    assert cell.nearest_label_km is None and cell.frames == 1


def test_frames_from_rows_reads_the_sql_usable_text():
    rows = [
        (47.0, 19.0, None, False, None),                    # no quality pass: usable
        (47.0, 19.0, "false", True, dt.date(2024, 1, 1)),
        (47.0, 19.0, "true", False, None),
    ]
    frames = cov.frames_from_rows(rows, frame_usable)
    assert [f.usable for f in frames] == [True, False, True]
    assert frames[1].labelled and frames[1].capture_date == dt.date(2024, 1, 1)


def test_render_has_every_section_and_canonical_class_labels():
    best = SCALE.best
    frames = [frame(INNER, labelled=True, capture_date=dt.date(2020, 1, 1)), frame(FAR)]
    segments = [seg(INNER, rqi=best, level="high", unlabelled_area=True)]
    stats = cov.summarize(frames, segments, TODAY)
    text = cov.render(stats, cov.unlabelled_cells(frames, [], top=20), TODAY, label_points=1)

    assert text.startswith("# Coverage & data-quality report — 2026-11-26")
    for heading in ("## Headline", "## Frames by area", "## Segments and km by class",
                    "## Confidence mix", "## Top 1 cells (1 km) with frames but no label"):
        assert heading in text
    assert f"{best} {SCALE.label(best, 'hu')}" in text
    assert "frames: 2 (2 usable, 0 unusable), human-labelled: 1 (50%)" in text
    assert "100% older than 3 y, 100% older than 5 y" in text
    assert "unlabelled_area: 1 segments, 0.2 km (100%)" in text
    assert "| TOTAL | 2 | 2 | 0 | 1 | 50% | 1 | 100% | 100% |" in text


def test_render_of_nothing_does_not_divide_by_zero():
    text = cov.render(cov.summarize([], [], TODAY), [], TODAY)
    assert "## Headline" in text and "frames: 0" in text
