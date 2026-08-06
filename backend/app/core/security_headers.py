"""
Security headers middleware.

WHY EACH HEADER IS HERE:
- X-Content-Type-Options: nosniff — stops browsers from "helpfully"
  guessing a different content type than what we declared (e.g. treating
  an uploaded image as HTML/JS if its content sniffs that way), which is
  a real vector for stored-XSS via file upload.
- X-Frame-Options: DENY — stops the site being embedded in an <iframe>
  on someone else's page, which is how clickjacking attacks work (a
  transparent iframe of our checkout button, over a fake button).
- Strict-Transport-Security — tells browsers "always use HTTPS for this
  origin from now on," even if someone links an http:// URL. Only sent
  in production (over an actual HTTPS deployment) — sending it during
  local http development would make the browser refuse to connect over
  plain http for the max-age duration, which breaks local dev.
- Referrer-Policy: strict-origin-when-cross-origin — avoids leaking full
  URLs (which can contain order IDs, tokens in query strings, etc — see
  the WebSocket token discussion in Phase 6) to third-party sites via the
  Referer header on outbound links.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
