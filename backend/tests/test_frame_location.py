"""Location defaults through SQLAlchemy's insert pipeline, without a DB server."""
import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import Session

from app.models.models import StreetViewImage, street_view_location


@pytest.mark.parametrize("latitude,longitude", [(None, 19.0), (47.5, None), (None, None)])
def test_unknown_coordinates_leave_location_unknown(latitude, longitude):
    assert street_view_location(latitude, longitude) is None


@pytest.mark.parametrize("mode", ["orm", "core_bulk", "orm_bulk"])
def test_model_default_sets_location_for_orm_and_core_inserts(mode):
    engine = create_engine("sqlite://")
    captured = []

    class CapturedInsert(Exception):
        pass

    @event.listens_for(engine, "before_cursor_execute")
    def capture_insert(conn, cursor, statement, parameters, context, executemany):
        # Defaults and GeoAlchemy bind conversion have run. Stop before SQLite
        # sees the INSERT: no schema, spatial extension or actual write needed.
        rows = parameters if executemany else [parameters]
        captured.extend(dict(zip(context.compiled.positiontup, row)) for row in rows)
        raise CapturedInsert

    payload = [{"latitude": 47.5, "longitude": 19.0}, {"latitude": 0.0, "longitude": 0.0}]
    try:
        with Session(engine) as session, pytest.raises(CapturedInsert):
            if mode == "orm":
                row = StreetViewImage()
                row.latitude, row.longitude = 47.5, 19.0  # Also covers assignment after construction.
                row.location = None
                session.add(row)
                session.flush()
            elif mode == "core_bulk":
                session.execute(insert(StreetViewImage.__table__), payload)
            else:
                session.execute(insert(StreetViewImage), payload)
    finally:
        engine.dispose()

    expected = payload[:1] if mode == "orm" else payload
    assert len(captured) == len(expected)
    for values, coordinates in zip(captured, expected):
        lat, lon = coordinates["latitude"], coordinates["longitude"]
        assert values["location"] == f"SRID=4326;POINT({lon} {lat})"
