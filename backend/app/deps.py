from fastapi import Header, HTTPException

from app.config import get_settings


async def require_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
) -> None:
    settings = get_settings()
    key = (x_api_key or "").strip()
    if not key and authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:].strip()
    if not key or key != settings.api_secret:
        raise HTTPException(status_code=403, detail="Invalid API key")
