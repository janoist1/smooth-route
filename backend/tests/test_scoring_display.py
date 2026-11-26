"""Product RQI comes only from usable DINO measurements (no PostGIS or model)."""
import datetime as dt
import json
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.core.rqi_scale import SCALE
from app.core.settings_manager import settings_manager
from app.graphql import queries
from app.models.models import StreetViewImage


def image(**overrides):
    values = dict(
        id=1, latitude=47.5, longitude=19.05, heading=90.0, pitch=-20.0,
        image_url="images/frame.jpg", rqi_score=float(SCALE.best),
        dino_rqi_score=None, damage_count=1, damage_types={"pothole": 1},
        analysis_metadata=None, created_at=dt.datetime(2026, 11, 26),
        pano_id="pano", capture_date=dt.date(2024, 1, 1),
    )
    return SimpleNamespace(**(values | overrides))


class PointSession:
    def __init__(self, images):
        self.images = images
        self.closed = False

    def query(self, model):
        return PointQuery(self.images if model is StreetViewImage else [])

    def close(self):
        self.closed = True


class PointQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def offset(self, *args):
        return self

    def limit(self, *args):
        return self

    def order_by(self, *args):
        return self

    def count(self):
        return len(self.rows)

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


def resolve_point(resolver):
    result = getattr(queries.Query(), resolver)(**({"id": 1} if resolver == "point" else {}))
    if resolver == "point":
        return result
    if resolver == "training_points":
        return result.items[0]
    return result[0]


@pytest.mark.parametrize("display_source", ["dino", "both", "yolo"])
@pytest.mark.parametrize("resolver", ["point", "points", "training_points"])
def test_missing_dino_is_unknown_even_with_excellent_yolo(monkeypatch, display_source, resolver):
    db = PointSession([image()])
    monkeypatch.setattr(queries, "get_db_session", lambda: db)
    monkeypatch.setattr(settings_manager, "get_setting", lambda *args: display_source)
    point = resolve_point(resolver)
    assert point.rqi_score is None
    assert point.rqi_source == "unknown"
    assert point.damage_types == {"pothole": 1}
    assert db.closed


@pytest.mark.parametrize("resolver", ["point", "points", "training_points"])
@pytest.mark.parametrize("usable", [None, True, False, " FALSE "])
def test_points_use_dino_and_respect_segment_frame_exclusions(monkeypatch, resolver, usable):
    meta = {"frame_quality": {"usable": usable}}
    db = PointSession([image(dino_rqi_score=float(SCALE.value_of("poor")), analysis_metadata=meta)])
    monkeypatch.setattr(queries, "get_db_session", lambda: db)
    monkeypatch.setattr(settings_manager, "get_setting", lambda *args: "both")
    point = resolve_point(resolver)
    expected = None if usable in (False, " FALSE ") else float(SCALE.value_of("poor"))
    assert point.rqi_score == expected
    assert point.rqi_source == ("unknown" if expected is None else "dino")
    assert point.analysis_metadata == meta


@pytest.fixture
def grid_db(monkeypatch):
    """Run the real grid SQL locally; emulate PostgreSQL JSON text extraction.

    SQLite's ->> returns 0/1 for JSON booleans; PostgreSQL returns false/true.
    The shim only bridges that database difference, leaving filtering and AVG
    to the SQL executed by the resolver.
    """
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def json_text(dbapi_connection, _record):
        def extract(value, key):
            child = json.loads(value).get(key) if value else None
            if child is None:
                return None
            return child if isinstance(child, str) else json.dumps(child)
        dbapi_connection.create_function("->>", 2, extract)

    with Session(engine) as db:
        db.execute(text("""
            CREATE TABLE street_view_images (
                latitude REAL, longitude REAL, rqi_score REAL,
                dino_rqi_score REAL, analysis_metadata TEXT
            )
        """))
        monkeypatch.setattr(queries, "get_db_session", lambda: db)
        yield db
    engine.dispose()


def add_grid_frame(db, *, dino=None, usable=None, longitude=19.05):
    meta = None if usable is None else {"frame_quality": {"usable": usable}}
    db.execute(text("""
        INSERT INTO street_view_images VALUES (47.5, :lng, :yolo, :dino, :meta)
    """), dict(lng=longitude, yolo=float(SCALE.best), dino=dino, meta=json.dumps(meta)))


def test_grid_skips_yolo_only_frames_instead_of_colouring_unknown(grid_db):
    add_grid_frame(grid_db)
    assert queries.Query().road_quality_grid(zoom=10)["cells"] == []


@pytest.mark.parametrize("usable", [False, "false", " FALSE "])
def test_grid_excludes_unusable_frames_before_averaging(grid_db, usable):
    add_grid_frame(grid_db, dino=float(SCALE.best))
    add_grid_frame(grid_db, dino=float(SCALE.value_of("poor")), usable=usable)
    # A cell containing only a rejected frame must disappear entirely.
    add_grid_frame(grid_db, dino=float(SCALE.best), usable=usable, longitude=19.15)
    cells = queries.Query().road_quality_grid(zoom=10)["cells"]
    assert len(cells) == 1
    assert cells[0][2] == float(SCALE.best)


def test_grid_keeps_usable_frames_and_bbox_filter(grid_db):
    add_grid_frame(grid_db, dino=float(SCALE.best), usable=True)
    add_grid_frame(grid_db, dino=float(SCALE.value_of("poor")))
    add_grid_frame(grid_db, dino=float(SCALE.best), longitude=19.15)
    cells = queries.Query().road_quality_grid(zoom=10, bbox=[19.0, 47.4, 19.1, 47.6])["cells"]
    assert len(cells) == 1
    assert cells[0][2] == (SCALE.best + SCALE.value_of("poor")) / 2


@pytest.mark.parametrize("is_dino", [False, True])
def test_training_stats_never_use_yolo_as_rqi(monkeypatch, is_dino):
    db = PointSession([
        image(),
        image(dino_rqi_score=SCALE.value_of("poor")),
        image(dino_rqi_score=SCALE.best, analysis_metadata={"frame_quality": {"usable": False}}),
    ])
    monkeypatch.setattr(queries, "get_db_session", lambda: db)
    result = queries.Query().training_stats(is_dino=is_dino)
    assert result.good_count == result.fair_count == 0
    assert result.poor_count == 1
    assert result.avg_rqi == SCALE.value_of("poor")
    assert sum(getattr(result, f"rqi{value}_count") for value in SCALE.values) == 1
    assert db.closed


def test_training_stats_preserve_manual_labels_over_dino(monkeypatch):
    class TrainingSession(PointSession):
        def query(self, model):
            if model is queries.TrainingDataModel:
                return PointQuery([SimpleNamespace(image_filename="frame.jpg", manual_rqi=SCALE.best)])
            return super().query(model)

    db = TrainingSession([image(dino_rqi_score=SCALE.value_of("poor"))])
    monkeypatch.setattr(queries, "get_db_session", lambda: db)
    result = queries.Query().training_stats()
    assert result.annotated == result.good_count == 1
    assert result.avg_rqi == SCALE.best


def test_cli_analyze_image_reports_damage_without_yolo_rqi(monkeypatch, tmp_path, capsys):
    from app import cli

    result = SimpleNamespace(
        rqi_score=SCALE.best, damage_count=2, damage_types={"pothole": 2}, analysis_metadata={},
    )
    monkeypatch.setitem(sys.modules, "app.services.road_quality", SimpleNamespace(
        road_quality_service=SimpleNamespace(analyze_image=lambda path: result),
    ))
    path = tmp_path / "frame.jpg"
    path.touch()
    cli.analyze_image(str(path))
    output = capsys.readouterr().out
    assert "Damage count: 2" in output
    assert "pothole: 2" in output
    assert "RQI" not in output
