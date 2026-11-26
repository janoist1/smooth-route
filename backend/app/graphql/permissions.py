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


class IsAuthenticatedUnlessPublicRead(IsAuthenticated):
    """Require auth normally, but allow anonymous on the round-1 public
    read-only deploy (no accounts there; route planning must work for anyone).
    Cost is capped by the Google Directions free tier + a GCP daily quota."""

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        from app.core.config import settings

        if settings.PUBLIC_READ_ONLY:
            return True
        return super().has_permission(source, info, **kwargs)


def admin_only_field(default: Any = None) -> Any:
    """A type field that resolves to null ([] for lists) for non-admins
    instead of failing the whole query.

    For admin data on publicly readable types, e.g. the labeller fields on
    Point (manual_rqi / manual_tags / manual_annotations / manual_comment):
        manual_comment: Optional[str] = admin_only_field()
    """
    import strawberry
    from strawberry.permission import PermissionExtension

    return strawberry.field(
        default=default,
        extensions=[PermissionExtension(permissions=[IsAdmin()], fail_silently=True)],
    )
