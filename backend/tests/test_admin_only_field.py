"""admin_only_field: admin data on a public type reads as null for others."""
import datetime
from typing import List, Optional

import strawberry

from app.core.auth import Identity
from app.graphql.permissions import admin_only_field
from app.graphql.types import Point


@strawberry.type
class Labelled:
    id: int
    manual_rqi: Optional[float] = admin_only_field()
    manual_tags: Optional[List[str]] = admin_only_field()


@strawberry.type
class ProbeQuery:
    @strawberry.field
    def item(self) -> Labelled:
        return Labelled(id=1, manual_rqi=3.0, manual_tags=["patch"])


probe = strawberry.Schema(query=ProbeQuery)
QUERY = "{ item { id manualRqi manualTags } }"


def run(identity):
    return probe.execute_sync(QUERY, context_value={"identity": identity})


def test_anonymous_and_user_get_null_without_errors():
    for identity in (None, Identity("u", "u", None, "user")):
        result = run(identity)
        assert result.errors is None
        assert result.data["item"]["id"] == 1
        assert result.data["item"]["manualRqi"] is None
        assert not result.data["item"]["manualTags"]


def test_admin_gets_the_value():
    result = run(Identity("a", "a", None, "admin"))
    assert result.errors is None
    assert result.data["item"] == {"id": 1, "manualRqi": 3.0, "manualTags": ["patch"]}


# --- the real Point type (T-82) ---------------------------------------------


@strawberry.type
class PointProbeQuery:
    @strawberry.field
    def point(self) -> Point:
        return Point(
            id=7, latitude=47.5, longitude=19.0, heading=0.0, pitch=None,
            image_url=None, rqi_score=2.0, damage_count=0, damage_types=None,
            analysis_metadata=None, created_at=datetime.datetime(2026, 1, 1),
            manual_rqi=4.0, manual_tags=["pothole"],
            manual_annotations=[{"label": "crack"}], manual_comment="owner note",
        )


point_probe = strawberry.Schema(query=PointProbeQuery)
POINT_QUERY = "{ point { id manualRqi manualTags manualAnnotations manualComment } }"


def run_point(identity):
    return point_probe.execute_sync(POINT_QUERY, context_value={"identity": identity})


def test_point_manual_fields_hidden_from_anonymous_and_user():
    for identity in (None, Identity("u", "u", None, "user")):
        result = run_point(identity)
        assert result.errors is None
        point = result.data["point"]
        assert point["id"] == 7
        assert point["manualRqi"] is None
        assert not point["manualTags"]
        assert not point["manualAnnotations"]
        assert point["manualComment"] is None


def test_point_manual_fields_visible_to_admin():
    result = run_point(Identity("a", "a", None, "admin"))
    assert result.errors is None
    assert result.data["point"] == {
        "id": 7,
        "manualRqi": 4.0,
        "manualTags": ["pothole"],
        "manualAnnotations": [{"label": "crack"}],
        "manualComment": "owner note",
    }
