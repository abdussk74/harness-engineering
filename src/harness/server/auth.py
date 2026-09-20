"""Bearer/API-key auth for the A2A server.

Built behind an `AuthScheme` protocol so OAuth2/mTLS can be added later
as a new implementation, not a redesign of call sites. v1 ships only
`BearerTokenAuth`; the middleware applies uniformly to every route
(JSON-RPC endpoint and Agent Card alike) — there's no unauthenticated
discovery path until signed cards (out of v1 scope) exist to make that
safe.
"""

from __future__ import annotations

from typing import Protocol

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class AuthScheme(Protocol):
    async def authenticate(self, request: Request) -> bool: ...


class BearerTokenAuth:
    """Accepts requests whose `Authorization: Bearer <token>` header matches
    a configured token."""

    def __init__(self, token: str) -> None:
        self._token = token

    async def authenticate(self, request: Request) -> bool:
        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        return scheme.lower() == "bearer" and value == self._token


_EXEMPT_PATHS = {"/healthz"}
"""Container liveness/readiness probes can't be expected to carry a
bearer token; this is the one deliberate hole in "auth on every route"."""


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, scheme: AuthScheme) -> None:
        super().__init__(app)
        self._scheme = scheme

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)
        if not await self._scheme.authenticate(request):
            return JSONResponse(
                {"error": "Unauthorized: missing or invalid bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)
