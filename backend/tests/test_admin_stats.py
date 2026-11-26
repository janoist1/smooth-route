"""Admin coverage counts use usable DINO classes, independently of YOLO."""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, create_engine
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.sql.elements import TextClause

from app.core.rqi_scale import SCALE
from app.core.timeutil import utcnow
from app import cli
from app.graphql import queries
from app.models.models import Job, User


@pytest.fixture
def stats_db(monkeypatch):
    # Only the frame columns these aggregates need; no PostGIS or external DB.
    base = declarative_base()

    class Frame(base):
        __tablename__ = "street_view_images"
        id = Column(Integer, primary_key=True)
        image_url = Column(String)
        latitude = Column(Float, default=47.5)
        longitude = Column(Float, default=19.05)
        heading = Column(Float, default=90.0)
        rqi_score = Column(Float)
        dino_rqi_score = Column(Float)
        analysis_metadata = Column(JSON)
        created_at = Column(DateTime, default=utcnow)

    class StatsSession(Session):
        def execute(self, statement, *args, **kwargs):
            # The unrelated per-day usage SQL uses PostgreSQL date functions.
            if isinstance(statement, TextClause):
                return SimpleNamespace(fetchall=lambda: [SimpleNamespace(day="2026-11-26", cnt=7)])
            return super().execute(statement, *args, **kwargs)

    engine = create_engine("sqlite://")
    base.metadata.create_all(engine)
    User.__table__.create(engine)
    Job.__table__.create(engine)
    with StatsSession(engine) as db:
        monkeypatch.setattr(queries, "StreetViewImage", Frame)
        monkeypatch.setattr(queries, "get_db_session", lambda: db)
        monkeypatch.setattr(cli, "StreetViewImage", Frame)
        monkeypatch.setattr(cli, "SessionLocal", lambda: db)

        def add(**values):
            db.add(Frame(**values))
            db.commit()

        yield add
    engine.dispose()


@pytest.mark.parametrize("yolo", SCALE.values)
def test_admin_stats_yolo_only_frame_is_unknown_not_a_level(stats_db, yolo):
    stats_db(rqi_score=yolo)
    result = queries.Query().admin_stats()
    assert result.total_points == result.total_images == result.images_this_month == 1
    assert result.analyzed_points == result.rqi_good == result.rqi_fair == result.rqi_poor == 0
    assert result.rqi_unknown == result.pending_analysis == 1
    assert result.rqi_unusable == 0


@pytest.mark.parametrize("usable", [False, "false", " FALSE "])
def test_admin_stats_unusable_frames_are_excluded_even_with_dino(stats_db, usable):
    metadata = {"frame_quality": {"usable": usable}}
    for level in SCALE.values:
        stats_db(dino_rqi_score=level, rqi_score=SCALE.best, analysis_metadata=metadata)
    stats_db(rqi_score=SCALE.best, analysis_metadata=metadata)
    result = queries.Query().admin_stats()
    assert result.analyzed_points == result.rqi_good == result.rqi_fair == result.rqi_poor == 0
    assert result.rqi_unusable == result.total_points == len(SCALE.values) + 1
    assert result.rqi_unknown == result.pending_analysis == 0


@pytest.mark.parametrize("scale", [SCALE, SCALE.mirrored()], ids=["canonical", "mirrored"])
def test_admin_stats_dino_buckets_follow_scale_and_partition_coverage(stats_db, monkeypatch, scale):
    monkeypatch.setattr(queries, "SCALE", scale)
    for level in scale.values:
        stats_db(dino_rqi_score=level, rqi_score=scale.best)
    stats_db(dino_rqi_score=scale.value_of("fair"), analysis_metadata={"frame_quality": {"usable": True}})
    stats_db(rqi_score=scale.best)
    stats_db(analysis_metadata={"dino_score": float(scale.best)})  # no ordinal DINO class
    stats_db(dino_rqi_score=scale.best, analysis_metadata={"frame_quality": {"usable": False}})
    # Usage totals keep counting rejected and unscored frames, including older ones.
    stats_db(created_at=dt.datetime(2000, 1, 1))
    result = queries.Query().admin_stats()
    assert (result.rqi_good, result.rqi_fair, result.rqi_poor) == (2, 2, 2)
    assert result.analyzed_points == 6
    assert result.rqi_unknown == result.pending_analysis == 3
    assert result.rqi_unusable == 1
    assert result.total_points == result.analyzed_points + result.rqi_unknown + result.rqi_unusable
    assert result.images_this_month == result.total_images - 1
    assert [(row.day, row.count) for row in result.images_per_day] == [("2026-11-26", 7)]


def test_admin_stats_empty_database_has_zero_coverage(stats_db):
    result = queries.Query().admin_stats()
    assert result.total_points == result.analyzed_points == result.pending_analysis == 0
    assert result.rqi_good == result.rqi_fair == result.rqi_poor == 0
    assert result.rqi_unknown == result.rqi_unusable == 0


def test_cli_list_points_counts_and_displays_only_usable_dino(stats_db, capsys):
    stats_db(rqi_score=SCALE.best)
    stats_db(rqi_score=SCALE.best, dino_rqi_score=SCALE.value_of("poor"))
    stats_db(dino_rqi_score=SCALE.best, analysis_metadata={"frame_quality": {"usable": False}})
    cli.list_points()
    output = capsys.readouterr().out
    summary = next(line for line in output.splitlines() if "Points with RQI" in line)
    assert "1" in summary
    assert output.count("No RQI") == 2
    assert output.count("RQI:") == 1
    assert f"RQI: {float(SCALE.value_of('poor'))}" in output
