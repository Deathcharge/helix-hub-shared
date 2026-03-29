"""
Sentry Error Tracking Service

Provides centralized error tracking and performance monitoring for the Helix SaaS platform.
"""

import logging
import os

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

logger = logging.getLogger(__name__)

# Sentry DSN from environment
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))


class SentryService:
    """Sentry integration service for error tracking and performance monitoring."""

    def __init__(self, dsn: str = SENTRY_DSN, environment: str = SENTRY_ENVIRONMENT) -> None:
        self.dsn = dsn
        self.environment = environment
        self.initialized = False

    def init_sentry(self) -> bool:
        """Initialize Sentry error tracking."""
        if not self.dsn:
            logger.warning("⚠️  Sentry DSN not configured - error tracking disabled")
            return False

        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.logging import LoggingIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

            # Configure Sentry
            sentry_sdk.init(
                dsn=self.dsn,
                environment=self.environment,
                traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
                profiles_sample_rate=0.1,
                # Include relevant integrations
                integrations=[
                    FastApiIntegration(),
                    SqlalchemyIntegration(),
                    LoggingIntegration(level=logging.INFO),
                ],
                # Configure before_send to filter noise
                before_send=lambda event, hint: self._filter_events(event, hint),
                # Set release version if available
                release=os.getenv("GIT_COMMIT_SHA", None),
            )

            self.initialized = True
            logger.info("✅ Sentry error tracking initialized")
            logger.info("   Environment: %s", self.environment)
            logger.info("   Traces sample rate: %s", SENTRY_TRACES_SAMPLE_RATE)

            return True

        except ImportError:
            logger.error("❌ sentry-sdk not installed - run: pip install sentry-sdk[fastapi]")
            return False
        except (ValueError, TypeError, KeyError) as e:
            logger.debug("Sentry configuration error: %s", e)
            return False
        except Exception as e:
            logger.error("❌ Failed to initialize Sentry: %s", e)
            return False

    def _filter_events(self, event: dict, hint: dict) -> dict | None:
        """Filter out noisy events before sending to Sentry."""
        # Filter out 404s from health checks
        if "exception" in hint:
            exc_value = hint.get("exception", {})
            if hasattr(exc_value, "values"):
                for exc in exc_value.values:
                    if hasattr(exc, "type"):
                        # Skip common non-critical errors
                        if exc.type in ("NotFound", "404"):
                            return None
                        # Filter out HTTP 429 (rate limit) noise
                        if "429" in str(exc):
                            return None

        return event

    def capture_exception(self, exception: Exception, extra: dict | None = None) -> str | None:
        """Capture an exception with optional extra context."""
        if not self.initialized:
            return None

        try:
            with sentry_sdk.configure_scope() as scope:
                if extra:
                    for key, value in extra.items():
                        scope.set_extra(key, value)

            return sentry_sdk.capture_exception(exception)
        except (ValueError, TypeError) as e:
            logger.debug("Sentry exception capture validation error: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to capture exception: %s", e)
            return None

    def capture_message(self, message: str, level: str = "info", extra: dict | None = None) -> str | None:
        """Capture a message with optional extra context."""
        if not self.initialized:
            return None

        try:
            with sentry_sdk.configure_scope() as scope:
                if extra:
                    for key, value in extra.items():
                        scope.set_extra(key, value)

            return sentry_sdk.capture_message(message, level=level)
        except Exception as e:
            logger.error("Failed to capture message: %s", e)
            return None

    def set_user_context(
        self,
        user_id: str,
        email: str | None = None,
        username: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Set user context for error tracking."""
        if not self.initialized:
            return

        try:
            sentry_sdk.set_user(
                {
                    "id": user_id,
                    "email": email,
                    "username": username,
                    "tenant_id": tenant_id,
                }
            )
        except Exception as e:
            logger.error("Failed to set user context: %s", e)

    def set_tag(self, key: str, value: str) -> None:
        """Set a tag for all future events."""
        if not self.initialized:
            return

        try:
            sentry_sdk.set_tag(key, value)
        except Exception as e:
            logger.error("Failed to set tag: %s", e)

    def add_breadcrumb(
        self,
        category: str,
        message: str,
        data: dict | None = None,
        level: str = "info",
    ) -> None:
        """Add a breadcrumb to the current trace."""
        if not self.initialized:
            return

        try:
            sentry_sdk.add_breadcrumb(
                {
                    "category": category,
                    "message": message,
                    "data": data or {},
                    "level": level,
                }
            )
        except Exception as e:
            logger.error("Failed to add breadcrumb: %s", e)


# Global Sentry service instance
sentry_service = SentryService()


def init_sentry() -> bool:
    """Initialize Sentry error tracking. Call this during app startup."""
    return sentry_service.init_sentry()
