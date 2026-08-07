# """
# Application entrypoint.

# WHY CORSMiddleware IS CONFIGURED EXPLICITLY:
# Browsers block cross-origin requests by default (frontend on :3000 calling
# backend on :8000 counts as cross-origin). Without this middleware, every
# fetch/axios call from the Next.js app would fail with a CORS error. We
# only allow origins listed in CORS_ORIGINS (env var) — never "*" in
# production, since that would let any website call our authenticated API
# using a logged-in user's cookies/tokens.

# MIDDLEWARE ORDER MATTERS:
# Starlette applies middleware in the reverse of the order added (the last
# one added runs first, outermost). RequestContextMiddleware is added last
# so it wraps everything else — every request gets a request_id and gets
# logged, even one that a lower middleware rejects. Security headers apply
# to every response, including error responses, for the same reason.

# WHY /docs AND /redoc ARE DISABLED IN PRODUCTION:
# Interactive API docs are extremely useful during development but also
# hand an attacker a complete, browsable map of every endpoint and its
# exact request/response shape. There's no code-level reason to expose
# that publicly once the API isn't actively being explored by the team
# building against it.
# """
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
# from slowapi import _rate_limit_exceeded_handler
# from slowapi.errors import RateLimitExceeded
# from slowapi.middleware import SlowAPIMiddleware

# from app.api.v1.admin_catalog import router as admin_catalog_router
# from app.api.v1.admin_coupons import router as admin_coupons_router
# from app.api.v1.admin_dashboard import router as admin_dashboard_router
# from app.api.v1.admin_orders import router as admin_orders_router
# from app.api.v1.admin_users import router as admin_users_router
# from app.api.v1.addresses import router as addresses_router
# from app.api.v1.auth import router as auth_router
# from app.api.v1.cart import router as cart_router
# from app.api.v1.catalog import router as catalog_router
# from app.api.v1.delivery import router as delivery_router
# from app.api.v1.notifications import router as notifications_router
# from app.api.v1.orders import router as orders_router
# from app.api.v1.payments import router as payments_router
# from app.api.v1.recommendations import router as recommendations_router
# from app.api.v1.reviews import router as reviews_router
# from app.api.v1.search import router as search_router
# from app.api.v1.ws import router as ws_router
# from app.core.config import settings
# from app.core.exception_handlers import register_exception_handlers
# from app.core.images import MEDIA_ROOT
# from app.core.rate_limit import limiter
# from app.core.request_context import RequestContextMiddleware, setup_logging
# from app.core.security_headers import SecurityHeadersMiddleware

# setup_logging()

# _is_production = settings.ENVIRONMENT == "production"

# app = FastAPI(
#     title="E-Commerce API",
#     version="0.7.0",
#     description=(
#         "Phase 1: Auth. Phase 2: Catalog. Phase 3: Cart/checkout/orders. "
#         "Phase 4: Razorpay payments. Phase 5: Admin panel. "
#         "Phase 6: Real-time tracking, notifications, search, recommendations, reviews. "
#         "Phase 7: Hardening (rate limiting, security headers, structured logging)."
#     ),
#     docs_url=None if _is_production else "/docs",
#     redoc_url=None if _is_production else "/redoc",
#     openapi_url=None if _is_production else "/openapi.json",
# )

# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# register_exception_handlers(app)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=settings.cors_origins_list,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# app.add_middleware(SlowAPIMiddleware)
# app.add_middleware(SecurityHeadersMiddleware)
# app.add_middleware(RequestContextMiddleware)

# MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
# # Serves uploaded product images directly — e.g. an image saved at
# # media/products/<id>/<file>.jpg becomes reachable at /media/products/<id>/<file>.jpg.
# # Fine for local/dev; production deployments serve this from S3/CDN instead
# # (see app/core/images.py docstring), at which point this mount goes away.
# app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")

# app.include_router(auth_router)
# app.include_router(addresses_router)
# app.include_router(catalog_router)
# app.include_router(admin_catalog_router)
# app.include_router(cart_router)
# app.include_router(orders_router)
# app.include_router(admin_orders_router)
# app.include_router(admin_coupons_router)
# app.include_router(payments_router)
# app.include_router(admin_users_router)
# app.include_router(admin_dashboard_router)
# app.include_router(reviews_router)
# app.include_router(notifications_router)
# app.include_router(ws_router)
# app.include_router(delivery_router)
# app.include_router(search_router)
# app.include_router(recommendations_router)


# @app.get("/health", tags=["health"])
# def health_check():
#     return {"status": "ok", "environment": settings.ENVIRONMENT}



"""
Application entrypoint.

WHY CORSMiddleware IS CONFIGURED EXPLICITLY:
Browsers block cross-origin requests by default (frontend on :3000 calling
backend on :8000 counts as cross-origin). Without this middleware, every
fetch/axios call from the Next.js app would fail with a CORS error. We
only allow origins listed in CORS_ORIGINS (env var) — never "*" in
production, since that would let any website call our authenticated API
using a logged-in user's cookies/tokens.

MIDDLEWARE ORDER MATTERS:
Starlette applies middleware in the reverse of the order added (the last
one added runs first, outermost). RequestContextMiddleware is added last
so it wraps everything else — every request gets a request_id and gets
logged, even one that a lower middleware rejects. Security headers apply
to every response, including error responses, for the same reason.

WHY /docs AND /redoc ARE DISABLED IN PRODUCTION:
Interactive API docs are extremely useful during development but also
hand an attacker a complete, browsable map of every endpoint and its
exact request/response shape. There's no code-level reason to expose
that publicly once the API isn't actively being explored by the team
building against it.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.admin_catalog import router as admin_catalog_router
from app.api.v1.admin_coupons import router as admin_coupons_router
from app.api.v1.admin_dashboard import router as admin_dashboard_router
from app.api.v1.admin_notifications import router as admin_notifications_router
from app.api.v1.admin_orders import router as admin_orders_router
from app.api.v1.admin_users import router as admin_users_router
from app.api.v1.addresses import router as addresses_router
from app.api.v1.auth import router as auth_router
from app.api.v1.cart import router as cart_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.delivery import router as delivery_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.orders import router as orders_router
from app.api.v1.payments import router as payments_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.search import router as search_router
from app.api.v1.ws import router as ws_router
from app.core.config import settings
from app.core.exception_handlers import UnhandledExceptionMiddleware, register_exception_handlers
from app.core.images import MEDIA_ROOT
from app.core.rate_limit import limiter
from app.core.request_context import RequestContextMiddleware, setup_logging
from app.core.security_headers import SecurityHeadersMiddleware

setup_logging()

_is_production = settings.ENVIRONMENT == "production"

app = FastAPI(
    title="E-Commerce API",
    version="0.7.0",
    description=(
        "Phase 1: Auth. Phase 2: Catalog. Phase 3: Cart/checkout/orders. "
        "Phase 4: Razorpay payments. Phase 5: Admin panel. "
        "Phase 6: Real-time tracking, notifications, search, recommendations, reviews. "
        "Phase 7: Hardening (rate limiting, security headers, structured logging)."
    ),
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_exception_handlers(app)

# WHY THIS IS ADDED *BEFORE* CORSMiddleware:
# Starlette applies middleware in the reverse of the order added (last
# added = outermost). Adding UnhandledExceptionMiddleware first means it
# ends up closer to the router than CORSMiddleware — so when it catches
# an exception and returns a JSONResponse itself, that response still
# passes back out through CORSMiddleware.__call__ afterward and gets the
# Access-Control-Allow-Origin header attached, same as any normal
# response. See app/core/exception_handlers.py's module docstring for
# why this can't be done with @app.exception_handler(Exception) instead
# (Starlette hoists that to ServerErrorMiddleware, which is always
# OUTSIDE every add_middleware() layer — the actual root cause of a real
# bug where a genuine 500 came back to the browser reporting a CORS
# error instead).
app.add_middleware(UnhandledExceptionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
# Serves uploaded product images directly — e.g. an image saved at
# media/products/<id>/<file>.jpg becomes reachable at /media/products/<id>/<file>.jpg.
# Fine for local/dev; production deployments serve this from S3/CDN instead
# (see app/core/images.py docstring), at which point this mount goes away.
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")

app.include_router(auth_router)
app.include_router(addresses_router)
app.include_router(catalog_router)
app.include_router(admin_catalog_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(admin_orders_router)
app.include_router(admin_coupons_router)
app.include_router(payments_router)
app.include_router(admin_users_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_notifications_router)
app.include_router(reviews_router)
app.include_router(notifications_router)
app.include_router(ws_router)
app.include_router(delivery_router)
app.include_router(search_router)
app.include_router(recommendations_router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
