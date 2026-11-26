"""GraphQL schema composition root.

Query resolvers live in queries.py, mutations in mutations.py, shared helpers
in resolver_helpers.py. This module only wires them into the Strawberry schema.
"""
import strawberry
from strawberry.tools import merge_types

from app.graphql.label_queue import LabelQueueMutation, LabelQueueQuery
from app.graphql.mutations import Mutation
from app.graphql.queries import Query

# Full schema for local dev / the always-on backend (reads + mutations).
# Feature modules with their own resolver classes (label queue) are merged in
# here instead of growing queries.py / mutations.py.
FullQuery = merge_types("Query", (Query, LabelQueueQuery))
FullMutation = merge_types("Mutation", (Mutation, LabelQueueMutation))
schema = strawberry.Schema(query=FullQuery, mutation=FullMutation)

# Read-only schema for the round-1 public deploy: query fields only, so no
# mutation (collection, analysis, training) is reachable. The Query module is
# torch-free at import time — the heavy code is lazy-imported inside the
# admin-only resolvers, which anonymous public callers never trigger.
read_schema = strawberry.Schema(query=Query)

