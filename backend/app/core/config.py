"""
Central application configuration.

WHY THIS FILE EXISTS:
Production apps never hardcode secrets, DB URLs, or environment-specific
values in code. Instead, everything configurable lives in environment
variables (.env locally, injected secrets in prod via Docker/K8s/Vercel).
pydantic-settings reads those env vars ONCE at startup, validates their
types, and gives the rest of the app a single typed `settings` object to
import — so nobody ever does `os.getenv("SECRET_KEY")` scattered across
50 files (which is untyped, unvalidated, and easy to typo).

WHY Settings() INSTANTIATION IS WRAPPED IN A try/except BELOW:
If required fields (DATABASE_URL, SECRET_KEY) are missing — most often
because nobody ran `cp .env.example .env` yet — pydantic-settings raises
a ValidationError, which crashes the app at IMPORT TIME, before Uvicorn
even binds to a port. In practice this is the single most common cause
of a confusing "CORS error" / "Failed to fetch" in the browser: the
frontend is trying to reach a backend that was never actually running,
and the browser's error message doesn't distinguish "no server" from
"server refused due to CORS." The try/except here turns a multi-line
pydantic traceback into one unambiguous, actionable message so this
failure mode is diagnosed in seconds instead of guessed at.
"""
import sys

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Database ---
    DATABASE_URL: str

    # --- JWT / Auth ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- App ---
    ENVIRONMENT: str = "development"
    # Both localhost and 127.0.0.1 are included by default: browsers treat
    # them as DIFFERENT origins even though they resolve to the same
    # machine, so a frontend opened via one while CORS_ORIGINS only lists
    # the other produces exactly the "No 'Access-Control-Allow-Origin'
    # header" browser error this project has hit in practice. Override
    # this env var with your real domain(s) in production — never "*"
    # (see main.py's CORSMiddleware setup for why).
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Razorpay ---
    # Sensible non-empty defaults so Settings() doesn't fail validation in
    # dev/test environments that haven't set real credentials — signature
    # verification (see core/razorpay_gateway.py) is pure HMAC math and
    # works fine against any secret, real or placeholder, as long as both
    # sides (the app and whoever's computing an expected signature) use
    # the same one. Production deployments MUST override these via env vars.
    RAZORPAY_KEY_ID: str = "rzp_test_placeholder_key_id"
    RAZORPAY_KEY_SECRET: str = "placeholder_key_secret_change_in_production"
    RAZORPAY_WEBHOOK_SECRET: str = "placeholder_webhook_secret_change_in_production"

    # --- Seed script (backend/seed.py) ---
    # Sensible defaults so `python seed.py` works out of the box on a fresh
    # clone with no .env edits required — override in .env for anything
    # beyond local dev. These three fields are what seed.py's seed_admin()
    # reads; without them defined here, Settings() simply has no such
    # attribute and seed.py raises AttributeError before writing any row
    # at all (the actual bug that was leaving fresh installs empty).
    DEFAULT_ADMIN_EMAIL: str = "admin@shopsphere.com"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@12345"
    DEFAULT_ADMIN_FULL_NAME: str = "ShopSphere Admin"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


def _load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        missing = [str(e["loc"][0]) for e in exc.errors() if e["type"] == "missing"]
        print(
            "\n"
            "=== Configuration error: backend cannot start ===\n"
            f"Missing required environment variable(s): {', '.join(missing) or '(see details below)'}\n"
            "\n"
            "Most likely cause: you haven't created backend/.env yet.\n"
            "Fix:\n"
            "    cd backend\n"
            "    cp .env.example .env\n"
            "    # then edit DATABASE_URL and SECRET_KEY if needed\n"
            "\n"
            f"Full validation error:\n{exc}\n"
            "===================================================\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


# Singleton instance — imported everywhere else as `from app.core.config import settings`
settings = _load_settings()
