"""GraphQL schema composition root.

Query resolvers live in queries.py, mutations in mutations.py, shared helpers
in resolver_helpers.py, request limits in limits.py. This module only wires
them into the Strawberry schema.
"""
import strawberry
from strawberry.tools import create_type, merge_types
from strawberry.types import get_object_definition

from app.graphql.label_queue import LabelQueueMutation, LabelQueueQuery, PairQueueQuery
from app.graphql.limits import schema_extensions
from app.graphql.model_admin import ModelAdminMutation, ModelAdminQuery
from app.graphql.mutations import Mutation
from app.graphql.route_alternatives import RouteAlternativesQuery
from app.graphql.queries import Query
from app.graphql.public_jobs import PublicJob, PublicJobQuery

# Full schema for local dev / the always-on backend (reads + mutations).
# Feature modules with their own resolver classes (label queue) are merged in
# here instead of growing queries.py / mutations.py.
FullQuery = merge_types(
    "Query", (Query, LabelQueueQuery, PairQueueQuery, RouteAlternativesQuery, ModelAdminQuery))
FullMutation = merge_types("Mutation", (Mutation, LabelQueueMutation, ModelAdminMutation))
schema = strawberry.Schema(
    query=FullQuery, mutation=FullMutation, extensions=schema_extensions(public=False),
    types=[PublicJob],  # Include the public status contract in the codegen SDL.
)

# Public roots are an explicit allow-list, independent of new full-schema
# fields. Reuse the field definitions with their resolvers, arguments, defaults
# and permissions (routeAlternatives allows anonymous callers in public mode).
# Job roots use a separate status type that cannot expose stored diagnostics.
# Keep the GraphQL name Query for existing fragments and Apollo's __typename.
_query_fields = {
    schema.config.name_converter.from_field(field): field
    for field in get_object_definition(FullQuery, strict=True).fields
}
PublicQuery = create_type("Query", [
    _query_fields[name] for name in (
        "me", "point", "points", "roadQualityGrid", "roadSegments",
        "routeQuality", "segmentFrames", "routeAlternatives",
    )
] + get_object_definition(PublicJobQuery, strict=True).fields)
# No mutation root; public extensions still disable introspection and mask
# unexpected errors in addition to the shared request limits.
read_schema = strawberry.Schema(query=PublicQuery, extensions=schema_extensions(public=True))
