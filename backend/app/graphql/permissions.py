"""Strawberry permission classes backed by the request identity.

The identity is resolved once per request in AuthGraphQL.get_context
(app/graphql/context.py) and read here from info.context["identity"].
"""
from typing import Any

from strawberry.permission import BasePermission
from strawberry.types import Info


class IsAuthenticated(BasePermission):
    message = "Authentication required"
    error_extensions = {"code": "UNAUTHENTICATED"}

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        return info.context.get("identity") is not None


class IsAdmin(BasePermission):
    message = "Admin privileges required"
    error_extensions = {"code": "FORBIDDEN"}

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        identity = info.context.get("identity")
        return identity is not None and identity.is_admin
