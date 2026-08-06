"""
Rate limiting.

WHY THESE SPECIFIC ENDPOINTS ARE LIMITED, NOT EVERYTHING:
- /auth/login and /auth/signup: the classic brute-force / credential-
  stuffing / fake-account-spam targets. A limit here matters far more
  than on, say, GET /products.
- /orders (checkout) and /payments/razorpay/orders: each successful call
  does real work (decrements stock, calls a paid external API) — a
  scripted flood here is both an abuse vector and a real cost, not just
  noise.
General browsing/catalog endpoints are deliberately NOT rate-limited in
this phase — over-limiting read traffic mostly just breaks legitimate
users (a customer scrolling a category page fires many requests fast)
for little security benefit.

WHY IN-MEMORY STORAGE FOR NOW, AND WHAT CHANGES IN PRODUCTION:
slowapi's default in-memory counter only works correctly for a single
process — same limitation as the WebSocket ConnectionManager in Phase 6
(see core/ws_manager.py). Two backend instances behind a load balancer
would each track their own counts, so a determined attacker could get
effectively 2x (or Nx) the intended limit by hitting different instances.
Production deployments point slowapi at Redis instead
(`Limiter(storage_uri="redis://...")`), giving every instance a shared
view of request counts — a one-line change once Redis is in the stack,
not a redesign.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Named so route decorators read like documentation:
# @limiter.limit(AUTH_RATE_LIMIT)
AUTH_RATE_LIMIT = "5/minute"
CHECKOUT_RATE_LIMIT = "10/minute"
PAYMENT_RATE_LIMIT = "10/minute"
