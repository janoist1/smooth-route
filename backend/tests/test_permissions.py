"""Strawberry permission guards: allowed/denied paths + real-schema wiring."""
import strawberry
import pytest

from app.core.auth import Identity
from app.graphql.permissions import IsAdmin, IsAuthenticated

USER = Identity(user_id="u1", clerk_id="user_1", email=None, role="user")
ADMIN = Identity(user_id="a1", clerk_id="admin_1", email=None, role="admin")


@strawberry.type
class ProbeQuery:
    @strawberry.field(permission_classes=[IsAuthenticated])
    def needs_user(self) -> str:
        return "ok"

    @strawberry.field(permission_classes=[IsAdmin])
    def needs_admin(self) -> str:
        return "ok"

    @strawberry.field
    def open_field(self) -> str:
        return "ok"


probe_schema = strawberry.Schema(query=ProbeQuery)


def run(query: str, identity):
    return probe_schema.execute_sync(query, context_value={"identity": identity})


class TestPermissionClasses:
    def test_anonymous_denied_everywhere_but_open(self):
        result = run("{ needsUser }", None)
        assert result.data is None
        assert "Authentication required" in result.errors[0].message

        result = run("{ needsAdmin }", None)
        assert "Admin privileges required" in result.errors[0].message

        result = run("{ openField }", None)
        assert result.errors is None and result.data["openField"] == "ok"

    def test_user_passes_auth_but_not_admin(self):
        result = run("{ needsUser }", USER)
        assert result.errors is None and result.data["needsUser"] == "ok"

        result = run("{ needsAdmin }", USER)
        assert result.data is None
        assert "Admin privileges required" in result.errors[0].message

    def test_admin_passes_both(self):
        assert run("{ needsUser }", ADMIN).errors is None
        assert run("{ needsAdmin }", ADMIN).errors is None

    def test_error_extensions_carry_codes(self):
        result = run("{ needsUser }", None)
        assert result.errors[0].extensions.get("code") == "UNAUTHENTICATED"
        result = run("{ needsAdmin }", USER)
        assert result.errors[0].extensions.get("code") == "FORBIDDEN"


@pytest.fixture(scope="module")
def schema():
    from app.graphql.schema import schema

    return schema


class TestRealSchemaWiring:
    """Denial paths on the production schema — guards fire before resolvers,
    so no DB/services are touched."""

    def exec(self, schema, query, identity):
        return schema.execute_sync(query, context_value={"identity": identity})

    def test_admin_mutations_denied_for_anonymous_and_user(self, schema):
        mutation = 'mutation { updateSetting(input: {key: "k", value: "1"}) { key } }'
        for identity in (None, USER):
            result = self.exec(schema, mutation, identity)
            assert result.data is None
            assert "Admin privileges required" in result.errors[0].message

    def test_training_mutations_denied_for_user(self, schema):
        mutation = 'mutation { saveTrainingData(input: {imageFilename: "x.jpg"}) }'
        result = self.exec(schema, mutation, USER)
        assert "Admin privileges required" in result.errors[0].message

    def test_process_route_requires_authentication(self, schema):
        mutation = (
            'mutation { processRoute(input: {origin: "a", destination: "b"}) { id } }'
        )
        result = self.exec(schema, mutation, None)
        assert result.data is None
        assert "Authentication required" in result.errors[0].message

    def test_settings_query_is_admin_only(self, schema):
        result = self.exec(schema, "{ settings { key } }", USER)
        assert "Admin privileges required" in result.errors[0].message

    def test_get_route_requires_authentication(self, schema):
        result = self.exec(
            schema, '{ getRoute(origin: "a", destination: "b") { points { lat } } }', None
        )
        assert "Authentication required" in result.errors[0].message

    def test_me_is_null_for_anonymous_and_populated_for_user(self, schema):
        result = self.exec(schema, "{ me { clerkId role } }", None)
        assert result.errors is None and result.data["me"] is None

        result = self.exec(schema, "{ me { clerkId role } }", USER)
        assert result.errors is None
        assert result.data["me"] == {"clerkId": "user_1", "role": "user"}

    def test_config_stays_anonymous(self, schema):
        result = self.exec(schema, "{ config }", None)
        assert result.errors is None
