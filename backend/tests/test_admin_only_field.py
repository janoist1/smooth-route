"""admin_only_field: admin data on a public type reads as null for others."""
from typing import List, Optional

import strawberry

from app.core.auth import Identity
from app.graphql.permissions import admin_only_field


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
