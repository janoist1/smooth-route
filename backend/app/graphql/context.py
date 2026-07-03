"""ASGI GraphQL app that resolves the caller identity into the context.

An invalid Bearer token yields identity=None plus auth_error — permissioned
fields then fail with UNAUTHENTICATED, while public fields keep working.
"""
from typing import Any, Optional, Union

from starlette.requests import Request
from starlette.responses import Response
from starlette.websockets import WebSocket
from strawberry.asgi import GraphQL

from app.core.auth import TokenVerificationError, resolve_identity


class AuthGraphQL(GraphQL):
    async def get_context(
        self,
        request: Union[Request, WebSocket],
        response: Optional[Response] = None,
    ) -> dict[str, Any]:
        identity = None
        auth_error = None
        try:
            identity = resolve_identity(request.headers.get("authorization"))
        except TokenVerificationError as exc:
            auth_error = str(exc)
        return {
            "request": request,
            "response": response,
            "identity": identity,
            "auth_error": auth_error,
        }
