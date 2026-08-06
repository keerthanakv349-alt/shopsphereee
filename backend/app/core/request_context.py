"""
Request ID propagation and structured logging.

WHY EVERY REQUEST GETS A UUID, ECHOED IN THE X-Request-ID RESPONSE HEADER:
When something goes wrong in production, "the checkout failed for a
customer around 3pm" is nearly useless for debugging — there are
thousands of requests around 3pm. If every log line for a request
includes the same request_id, and that ID is also visible to the
frontend (which can show it in an error message: "Something went wrong.
Reference: a1b2c3d4"), a support engineer can grep logs for that exact ID
and see the ENTIRE request's story — which endpoint, which user, what
failed — instead of guessing. This is standard practice in any
production system handling real traffic.

WHY STRUCTURED (JSON) LOGS, NOT PLAIN TEXT:
Plain text logs ("User 123 logged in at 3pm") are fine for a human
tailing a file, but production log volumes get shipped to a log
aggregator (Datadog, CloudWatch, ELK) that needs to FILTER and QUERY
logs — "show me all 500 errors for user_id=123 in the last hour." That
requires structured fields, not prose. Emitting JSON lines means every
field (request_id, path, status_code, duration_ms) is queryable from day
one, without a later migration.
"""
import json
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ContextVar (not a plain global) because multiple requests are handled
# concurrently on the same event loop — a global variable would let one
# request's ID leak into another's log lines under concurrency.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        start = time.monotonic()
        logger = logging.getLogger("app.request")

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(f"Unhandled exception for {request.method} {request.url.path}")
            request_id_ctx.reset(token)
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
        response.headers["X-Request-ID"] = request_id
        request_id_ctx.reset(token)
        return response
