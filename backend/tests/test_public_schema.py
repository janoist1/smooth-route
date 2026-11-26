"""Public SDL boundary and compatibility with anonymous frontend operations."""
import re
from pathlib import Path

import pytest
from graphql import introspection_from_schema, parse, validate
from graphql.language import OperationDefinitionNode, OperationType
from strawberry.types import get_object_definition

from app.core.auth import Identity
from app.graphql.schema import FullQuery, PublicQuery, read_schema, schema


PUBLIC_QUERY_FIELDS = {
    "me", "point", "points", "roadQualityGrid", "roadSegments", "routeQuality",
    "segmentFrames", "job", "activeJob", "routeAlternatives",
}
ADMIN_QUERY_FIELDS = {
    "config", "settings", "availableModels", "rqiModelInfo", "adminStats",
    "trainingPoints", "trainingStats", "nextTrainingPoint", "labelQueue",
    "labelExamples", "pairQueue", "modelAdmin",
}


@pytest.fixture(scope="module")
def public_introspection():
    # Inspect the actual schema in-process without enabling HTTP introspection
    # or changing the production extensions that intentionally prohibit it.
    return introspection_from_schema(read_schema._schema)["__schema"]


def test_public_query_fields_equal_allow_list(public_introspection):
    assert public_introspection["queryType"]["name"] == "Query"
    query = next(t for t in public_introspection["types"] if t["name"] == "Query")
    assert {field["name"] for field in query["fields"]} == PUBLIC_QUERY_FIELDS


def test_public_schema_has_no_mutation_type(public_introspection):
    assert public_introspection["mutationType"] is None
    assert "Mutation" not in {t["name"] for t in public_introspection["types"]}


def test_full_schema_keeps_admin_and_feature_roots():
    full = introspection_from_schema(schema._schema)["__schema"]
    query = next(t for t in full["types"] if t["name"] == "Query")
    assert ADMIN_QUERY_FIELDS | PUBLIC_QUERY_FIELDS | {"getRoute"} == {
        field["name"] for field in query["fields"]
    }
    assert full["mutationType"]["name"] == "Mutation"
    mutation = next(t for t in full["types"] if t["name"] == "Mutation")
    assert {"processRoute", "quickLabel", "submitPairJudgment", "startRetrain"} <= {
        field["name"] for field in mutation["fields"]
    }


@pytest.mark.parametrize("identity", [
    None, Identity(user_id="admin", clerk_id="admin", email=None, role="admin"),
], ids=["anonymous", "admin"])
def test_public_rejects_non_public_roots_during_validation(identity):
    excluded = ADMIN_QUERY_FIELDS | {"getRoute"}
    result = read_schema.execute_sync(
        "{ " + " ".join(sorted(excluded)) + " }", context_value={"identity": identity}
    )
    assert result.data is None
    assert result.errors
    assert {error.nodes[0].name.value for error in result.errors} == excluded
    assert all(error.message.startswith("Cannot query field") for error in result.errors)


def test_public_fields_reuse_resolvers_arguments_and_permissions():
    def fields(query):
        return {
            schema.config.name_converter.from_field(field): field
            for field in get_object_definition(query, strict=True).fields
        }

    full, public = fields(FullQuery), fields(PublicQuery)
    for name in PUBLIC_QUERY_FIELDS:
        assert public[name].base_resolver is full[name].base_resolver, name
        assert public[name].arguments == full[name].arguments, name
        assert public[name].permission_classes == full[name].permission_classes, name
        assert public[name].extensions == full[name].extensions, name


def test_anonymous_frontend_operations_validate_against_public_schema():
    src = Path(__file__).resolve().parents[2] / "frontend/src"
    if not src.is_dir():
        pytest.skip("frontend sources not present")
    operations = {}
    for relative_path in (
        "modules/auth/viewer.tsx", "modules/api/sagas.ts", "modules/map/sagas.ts",
        "modules/map/segments/api.ts",
    ):
        for source in re.findall(r"gql\(\s*`([^`]*)`", (src / relative_path).read_text()):
            document = parse(source)
            operation = next(d for d in document.definitions if isinstance(d, OperationDefinitionNode))
            if operation.operation == OperationType.QUERY:
                operations[operation.name.value] = document

    assert set(operations) == {
        "Viewer", "GetJob", "GetPoints", "GetRoadQualityGrid", "GetPointDetail",
        "RouteAlternatives", "GetActiveJob", "GetRoadSegments", "GetRouteQuality",
        "GetSegmentFrames",
    }
    for name, document in operations.items():
        assert not validate(read_schema._schema, document), name
