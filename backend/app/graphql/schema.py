"""GraphQL schema composition root.

Query resolvers live in queries.py, mutations in mutations.py, shared helpers
in resolver_helpers.py. This module only wires them into the Strawberry schema.
"""
import strawberry

from app.graphql.mutations import Mutation
from app.graphql.queries import Query

# Full schema for local dev / the always-on backend (reads + mutations).
schema = strawberry.Schema(query=Query, mutation=Mutation)

# Read-only schema for the round-1 public deploy: query fields only, so no
# mutation (collection, analysis, training) is reachable. The Query module is
# torch-free at import time — the heavy code is lazy-imported inside the
# admin-only resolvers, which anonymous public callers never trigger.
read_schema = strawberry.Schema(query=Query)

