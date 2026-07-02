"""GraphQL schema composition root.

Query resolvers live in queries.py, mutations in mutations.py, shared helpers
in resolver_helpers.py. This module only wires them into the Strawberry schema.
"""
import strawberry

from app.graphql.mutations import Mutation
from app.graphql.queries import Query

schema = strawberry.Schema(query=Query, mutation=Mutation)
