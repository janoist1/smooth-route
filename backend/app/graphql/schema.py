"""GraphQL schema composition root.

Query resolvers live in queries.py, mutations in mutations.py, shared helpers
in resolver_helpers.py, request limits in limits.py. This module only wires
them into the Strawberry schema.
"""
import strawberry
from strawberry.tools import merge_types

from app.graphql.label_queue import LabelQueueMutation, LabelQueueQuery, PairQueueQuery
from app.graphql.limits import schema_extensions
from app.graphql.mutations import Mutation
from app.graphql.route_alternatives import RouteAlternativesQuery
from app.graphql.queries import Query

# Full schema for local dev / the always-on backend (reads + mutations).
# Feature modules with their own resolver classes (label queue) are merged in
# here instead of growing queries.py / mutations.py.
FullQuery = merge_types("Query", (Query, LabelQueueQuery, PairQueueQuery, RouteAlternativesQuery))
FullMutation = merge_types("Mutation", (Mutation, LabelQueueMutation))
schema = strawberry.Schema(
    query=FullQuery, mutation=FullMutation, extensions=schema_extensions(public=False)
)

# Read-only schema for the round-1 public deploy: query fields only, so no
# mutation (collection, analysis, training) is reachable. The Query module is
# torch-free at import time — the heavy code is lazy-imported inside the
# admin-only resolvers, which anonymous public callers never trigger.
# Public = introspection off and unexpected errors masked (limits.py).
# Route alternatives ride along on the public schema like getRoute does.
ReadQuery = merge_types("Query", (Query, RouteAlternativesQuery))
read_schema = strawberry.Schema(query=ReadQuery, extensions=schema_extensions(public=True))
