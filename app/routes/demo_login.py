"""Demo-portal login with the platform test account from .env (DEMO_LOGIN_USERNAME /
DEMO_LOGIN_PASSWORD). The backend logs in to the platform itself and hands the browser
only the access token, so the password never leaves the server. Both endpoints 404
when the account isn't configured."""
import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key
from app.config import settings

router = APIRouter(prefix="/demo-login", tags=["demo"], dependencies=[Depends(require_api_key)])

# No API key on this one: it is how the portal gets the key (DEMO_PORTAL_AUTOFILL_API_KEY).
config_router = APIRouter(tags=["demo"])


@config_router.get("/demo-config")
async def demo_config():
    if not (settings.DEMO_PORTAL_AUTOFILL_API_KEY and settings.API_KEY):
        raise HTTPException(status_code=404, detail="Demo portal autofill is not enabled")
    return {"apiKey": settings.API_KEY}


def _require_configured() -> None:
    if not (settings.DEMO_LOGIN_USERNAME and settings.DEMO_LOGIN_PASSWORD):
        raise HTTPException(status_code=404, detail="Demo login is not configured")


@router.get("")
async def demo_login_info():
    _require_configured()
    return {"username": settings.DEMO_LOGIN_USERNAME}


@router.post("")
async def demo_login():
    _require_configured()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.PLATFORM_API_BASE_URL}/auth/v1/auth/login",
                json={"username": settings.DEMO_LOGIN_USERNAME, "password": settings.DEMO_LOGIN_PASSWORD},
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Platform login is unreachable")
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Platform login failed: {data.get('message') or resp.status_code}")
    access_token = (data.get("token") or {}).get("accessToken")
    if not access_token:
        raise HTTPException(status_code=502, detail="Platform login response missing token.accessToken")
    return {"accessToken": access_token, "username": settings.DEMO_LOGIN_USERNAME}
