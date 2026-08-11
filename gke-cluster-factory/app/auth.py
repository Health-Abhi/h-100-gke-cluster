from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


async def enforce_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.api_token:
        return
    supplied = credentials.credentials if credentials else ""
    if not hmac.compare_digest(supplied, settings.api_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token")


def actor_from_request(request: Request) -> str:
    for header in (
        "X-Goog-Authenticated-User-Email",
        "X-Forwarded-Email",
        "X-User-Email",
    ):
        value = request.headers.get(header)
        if value:
            return value.removeprefix("accounts.google.com:")
    return "local-user"
