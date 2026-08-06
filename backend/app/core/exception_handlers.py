# """
# Centralized exception handling.

# WHY UNHANDLED EXCEPTIONS DON'T JUST RETURN FASTAPI'S DEFAULT 500:
# Without a handler, an unexpected error (a bug, a DB hiccup) returns
# FastAPI's default response, which in debug contexts can include a full
# Python traceback — file paths, line numbers, sometimes local variable
# values. Leaking that to a client is a real information-disclosure risk
# (it can reveal internal structure, library versions, occasionally
# secrets sitting in a local variable). This handler replaces that with a
# generic message and the request_id (see request_context.py) — enough for
# a support engineer to find the real error in the logs, not enough for an
# attacker to learn about the internals.

# WHY THE FULL DETAILS STILL SHOW WHEN ENVIRONMENT=development:
# Hiding errors from the developer running the app locally would make
# debugging significantly more annoying for no security benefit — nobody
# untrusted is looking at a local dev server's responses. The environment
# check keeps the safety behavior for anything that isn't explicitly
# development.
# """
# import logging

# from fastapi import FastAPI, Request, status
# from fastapi.encoders import jsonable_encoder
# from fastapi.exceptions import RequestValidationError
# from fastapi.responses import JSONResponse
# from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# from app.core.config import settings
# from app.core.request_context import request_id_ctx

# logger = logging.getLogger("app.errors")


# def register_exception_handlers(app: FastAPI) -> None:
#     @app.exception_handler(RequestValidationError)
#     async def validation_exception_handler(request: Request, exc: RequestValidationError):
#         # Pydantic's default validation error body is already
#         # client-safe (it just lists which fields failed and why) — we
#         # only standardize the envelope shape here, not hide anything.
#         # jsonable_encoder matters: a custom validator that raises
#         # ValueError (see SignupRequest.password_complexity) puts that
#         # exception object in the error's `ctx`, which plain json.dumps
#         # can't serialize — jsonable_encoder converts it to a string first.
#         return JSONResponse(
#             status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
#             content={"detail": jsonable_encoder(exc.errors()), "request_id": request_id_ctx.get()},
#         )

#     @app.exception_handler(IntegrityError)
#     async def integrity_error_handler(request: Request, exc: IntegrityError):
#         # Almost always a unique/foreign-key constraint violation — most
#         # routes already pre-check for these (e.g. "does this email
#         # already exist?" before inserting) and return a clean 409
#         # themselves, so reaching this handler usually means a RACE
#         # CONDITION slipped past that pre-check (two signups with the
#         # same email landing at nearly the same instant). 409 Conflict is
#         # the correct status either way: the request conflicts with the
#         # current state of the data, not a client input error (422) or a
#         # server bug (500). The raw exception (which includes the SQL
#         # statement and parameter values in its string form — a real
#         # information leak, and exactly what issue #7 asks to avoid) is
#         # logged for debugging but never sent to the client.
#         request_id = request_id_ctx.get()
#         logger.warning(f"IntegrityError (request_id={request_id}): {exc.orig}")
#         return JSONResponse(
#             status_code=status.HTTP_409_CONFLICT,
#             content={
#                 "detail": "This request conflicts with existing data (e.g. a duplicate entry). "
#                 "Please check your input and try again.",
#                 "request_id": request_id,
#             },
#         )

#     @app.exception_handler(SQLAlchemyError)
#     async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
#         # Any other database-layer failure (connection drop, timeout,
#         # a real bug in a query) — never IntegrityError specifically
#         # (that has its own handler above, registered separately since
#         # FastAPI matches the most specific exception type). Treated the
#         # same as any other unexpected server error: logged in full,
#         # reported to the client generically.
#         request_id = request_id_ctx.get()
#         logger.exception(f"Unhandled SQLAlchemyError (request_id={request_id})")
#         detail = (
#             f"{type(exc).__name__}: {exc}"
#             if settings.ENVIRONMENT == "development"
#             else "A database error occurred. Please try again or contact support."
#         )
#         return JSONResponse(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             content={"detail": detail, "request_id": request_id},
#         )

#     @app.exception_handler(Exception)
#     async def unhandled_exception_handler(request: Request, exc: Exception):
#         request_id = request_id_ctx.get()
#         logger.exception(f"Unhandled exception (request_id={request_id})")

#         if settings.ENVIRONMENT == "development":
#             detail = f"{type(exc).__name__}: {exc}"
#         else:
#             detail = "An unexpected error occurred. Please try again or contact support."

#         return JSONResponse(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             content={"detail": detail, "request_id": request_id},
#         )


"""
Centralized exception handling.

WHY UNHANDLED EXCEPTIONS DON'T JUST RETURN FASTAPI'S DEFAULT 500:
Without a handler, an unexpected error (a bug, a DB hiccup) returns
FastAPI's default response, which in debug contexts can include a full
Python traceback — file paths, line numbers, sometimes local variable
values. Leaking that to a client is a real information-disclosure risk
(it can reveal internal structure, library versions, occasionally
secrets sitting in a local variable). This handler replaces that with a
generic message and the request_id (see request_context.py) — enough for
a support engineer to find the real error in the logs, not enough for an
attacker to learn about the internals.

WHY THE FULL DETAILS STILL SHOW WHEN ENVIRONMENT=development:
Hiding errors from the developer running the app locally would make
debugging significantly more annoying for no security benefit — nobody
untrusted is looking at a local dev server's responses. The environment
check keeps the safety behavior for anything that isn't explicitly
development.

WHY THE CATCH-ALL IS A MIDDLEWARE, NOT AN @app.exception_handler(Exception):
This is the root cause of a real bug: any unexpected exception (e.g. the
`razorpay` SDK raising when given invalid/placeholder credentials —
see api/v1/payments.py -> create_razorpay_order) came back to the browser
as "blocked by CORS policy: No 'Access-Control-Allow-Origin' header" on
top of the 500 — even though CORSMiddleware is configured correctly and
demonstrably adds the header to every other kind of error response
(422s, 409s, 429s all get it fine).

The reason is a Starlette internal detail, not a CORS misconfiguration:
Starlette special-cases any handler registered for the literal `Exception`
class (or status code 500) — it does NOT install it into the same
ExceptionMiddleware that RequestValidationError/IntegrityError/
SQLAlchemyError handlers use (which sits *inside* all app.add_middleware()
layers, including CORSMiddleware). Instead it wires it into
ServerErrorMiddleware, which Starlette always places as the absolute
OUTERMOST layer of the entire app — outside every middleware added via
add_middleware(), no matter what order they were added in. So the
response this handler builds physically never passes back through
CORSMiddleware.__call__ on its way out, and the browser correctly reports
no CORS header on it (there wasn't one to see, from its perspective).

The fix: implement the same "log it, return a generic message" behavior
as a genuine ASGI middleware (UnhandledExceptionMiddleware) that wraps
call_next() in try/except and returns the JSONResponse *itself*, at the
point in the stack where it's added. Middleware — unlike an
Exception-keyed handler — never gets hoisted out of the normal stack, so
as long as it's added BEFORE CORSMiddleware (see app/main.py — earlier
app.add_middleware() calls end up closer to the router, i.e. "inside"
later ones), any response it returns still passes back out through
CORSMiddleware like a normal response would, and gets the header attached
correctly. This fixes the CORS symptom for ANY future unhandled
exception anywhere in the app, not just this one payments endpoint.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.core.request_context import request_id_ctx

logger = logging.getLogger("app.errors")


class UnhandledExceptionMiddleware(BaseHTTPMiddleware):
    """Catch-all for exceptions with no specific handler — see the module
    docstring above for exactly why this has to be a middleware (added in
    app/main.py, positioned before CORSMiddleware) rather than
    `@app.exception_handler(Exception)`. Behavior is otherwise identical
    to what that handler used to do: log the full exception server-side,
    return a generic message to the client (full detail only in
    ENVIRONMENT=development), tagged with the request_id.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 - intentionally broad, this IS the catch-all
            request_id = request_id_ctx.get()
            logger.exception(f"Unhandled exception (request_id={request_id})")

            if settings.ENVIRONMENT == "development":
                detail = f"{type(exc).__name__}: {exc}"
            else:
                detail = "An unexpected error occurred. Please try again or contact support."

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": detail, "request_id": request_id},
            )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # Pydantic's default validation error body is already
        # client-safe (it just lists which fields failed and why) — we
        # only standardize the envelope shape here, not hide anything.
        # jsonable_encoder matters: a custom validator that raises
        # ValueError (see SignupRequest.password_complexity) puts that
        # exception object in the error's `ctx`, which plain json.dumps
        # can't serialize — jsonable_encoder converts it to a string first.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": jsonable_encoder(exc.errors()), "request_id": request_id_ctx.get()},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        # Almost always a unique/foreign-key constraint violation — most
        # routes already pre-check for these (e.g. "does this email
        # already exist?" before inserting) and return a clean 409
        # themselves, so reaching this handler usually means a RACE
        # CONDITION slipped past that pre-check (two signups with the
        # same email landing at nearly the same instant). 409 Conflict is
        # the correct status either way: the request conflicts with the
        # current state of the data, not a client input error (422) or a
        # server bug (500). The raw exception (which includes the SQL
        # statement and parameter values in its string form — a real
        # information leak, and exactly what issue #7 asks to avoid) is
        # logged for debugging but never sent to the client.
        request_id = request_id_ctx.get()
        logger.warning(f"IntegrityError (request_id={request_id}): {exc.orig}")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "This request conflicts with existing data (e.g. a duplicate entry). "
                "Please check your input and try again.",
                "request_id": request_id,
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        # Any other database-layer failure (connection drop, timeout,
        # a real bug in a query) — never IntegrityError specifically
        # (that has its own handler above, registered separately since
        # FastAPI matches the most specific exception type). Treated the
        # same as any other unexpected server error: logged in full,
        # reported to the client generically.
        request_id = request_id_ctx.get()
        logger.exception(f"Unhandled SQLAlchemyError (request_id={request_id})")
        detail = (
            f"{type(exc).__name__}: {exc}"
            if settings.ENVIRONMENT == "development"
            else "A database error occurred. Please try again or contact support."
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": detail, "request_id": request_id},
        )

    # NOTE: the generic catch-all is intentionally NOT registered here as
    # @app.exception_handler(Exception) — see this module's docstring for
    # why that breaks CORS headers on unexpected errors. It's registered
    # as UnhandledExceptionMiddleware via app.add_middleware() in
    # app/main.py instead, positioned before CORSMiddleware so its
    # responses still pass back through it correctly.
