"""
Helix Policy Enforcement Middleware
====================================

FastAPI middleware for automatic policy enforcement on API requests.

Features:
- Automatic policy evaluation on requests
- Configurable scope-based enforcement
- Audit logging integration
- Graceful error handling

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from apps.backend.services.policy_engine import (
    PolicyDecision,
    PolicyEngine,
    PolicyScope,
    get_policy_engine,
)

logger = logging.getLogger(__name__)


class PolicyEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces policies on incoming requests.
    
    Evaluates policies before the request reaches the endpoint handler.
    Can be configured to enforce different policies for different routes.
    """

    def __init__(
        self,
        app: FastAPI,
        *,
        enforce_on: set[str] | None = None,
        skip_on: set[str] | None = None,
        default_scope: PolicyScope = PolicyScope.API,
        audit_all: bool = True,
        deny_code: int = 403,
        deny_message: str = "Access denied by policy",
    ):
        """
        Initialize policy enforcement middleware.
        
        Args:
            app: FastAPI application
            enforce_on: Set of path prefixes to enforce policies on (None = all)
            skip_on: Set of path prefixes to skip policy enforcement
            default_scope: Default policy scope for evaluation
            audit_all: Whether to audit all requests (not just denials)
            deny_code: HTTP status code for denied requests
            deny_message: Default message for denied requests
        """
        super().__init__(app)
        self.enforce_on = enforce_on
        self.skip_on = skip_on or set()
        self.default_scope = default_scope
        self.audit_all = audit_all
        self.deny_code = deny_code
        self.deny_message = deny_message

        # Routes that should be skipped (health, docs, etc.)
        self._default_skip_routes = {
            "/health",
            "/healthz",
            "/ready",
            "/readyz",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through policy engine."""

        # Check if we should skip this path
        path = request.url.path

        if self._should_skip(path):
            return await call_next(request)

        # Build evaluation context
        context = self._build_context(request)

        # Evaluate policies
        engine = get_policy_engine()
        decision = engine.evaluate(context, scope=self.default_scope)

        # Log if auditing
        if self.audit_all or not decision.allowed:
            self._log_decision(request, decision)

        # Handle denial
        if not decision.allowed:
            return self._deny_response(decision)

        # Continue to endpoint
        response = await call_next(request)

        # Add policy headers to response
        self._add_policy_headers(response, decision)

        return response

    def _should_skip(self, path: str) -> bool:
        """Check if policy enforcement should be skipped for this path."""
        # Skip default routes
        if path in self._default_skip_routes:
            return True

        # Skip configured paths
        if path in self.skip_on:
            return True

        for skip_prefix in self.skip_on:
            if path.startswith(skip_prefix):
                return True

        # If enforce_on is specified, only enforce on those paths
        if self.enforce_on is not None:
            for prefix in self.enforce_on:
                if path.startswith(prefix):
                    return False
            return True  # Not in enforce_on, skip

        return False

    def _build_context(self, request: Request) -> dict[str, Any]:
        """Build evaluation context from request."""
        context = {
            "api": {
                "endpoint": request.url.path,
                "method": request.method,
                "query_params": dict(request.query_params),
                "headers": self._get_safe_headers(request),
            },
            "request": {
                "path": request.url.path,
                "method": request.method,
                "client_ip": self._get_client_ip(request),
                "user_agent": request.headers.get("user-agent", ""),
            },
            "timestamp": time.time(),
        }

        # Add user context if available (from auth middleware)
        user = getattr(request.state, "user", None)
        if user:
            if isinstance(user, dict):
                context["user"] = user
            else:
                context["user"] = {
                    "id": getattr(user, "id", None),
                    "email": getattr(user, "email", None),
                    "role": getattr(user, "role", None),
                    "authenticated": True,
                }
        else:
            context["user"] = {"authenticated": False}

        # Add session context if available
        session = getattr(request.state, "session", None)
        if session:
            context["session"] = {
                "id": getattr(session, "id", None),
            }

        return context

    def _get_safe_headers(self, request: Request) -> dict[str, str]:
        """Get headers safe for logging (redact sensitive ones)."""
        sensitive_headers = {
            "authorization",
            "x-api-key",
            "x-auth-token",
            "cookie",
        }

        headers = {}
        for key, value in request.headers.items():
            if key.lower() in sensitive_headers:
                headers[key] = "[REDACTED]"
            else:
                headers[key] = value

        return headers

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP from request."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

        if request.client:
            return request.client.host

        return "unknown"

    def _log_decision(self, request: Request, decision: PolicyDecision) -> None:
        """Log policy decision for audit."""
        log_data = {
            "path": request.url.path,
            "method": request.method,
            "allowed": decision.allowed,
            "effect": decision.effect.value,
            "matched_rules": decision.matched_rules,
            "denied_by": decision.denied_by,
            "warnings": decision.warnings,
        }

        if decision.allowed:
            logger.info("Policy decision: %s", log_data)
        else:
            logger.warning("Policy DENIED: %s", log_data)

    def _deny_response(self, decision: PolicyDecision) -> JSONResponse:
        """Create a denial response."""
        message = self.deny_message
        if decision.denied_by:
            message = f"{message}: {', '.join(decision.denied_by)}"

        return JSONResponse(
            status_code=self.deny_code,
            content={
                "error": "policy_denied",
                "message": message,
                "denied_by": decision.denied_by,
                "warnings": decision.warnings,
            },
        )

    def _add_policy_headers(self, response: Response, decision: PolicyDecision) -> None:
        """Add policy-related headers to response."""
        response.headers["X-Policy-Decision"] = decision.effect.value
        if decision.warnings:
            response.headers["X-Policy-Warnings"] = "; ".join(decision.warnings)


class AgentPolicyEnforcer:
    """
    Helper class for enforcing policies on agent actions.
    
    Use this within agent handlers to check permissions before
    performing sensitive operations.
    """

    def __init__(self, engine: PolicyEngine | None = None):
        self.engine = engine or get_policy_engine()

    def check(
        self,
        agent_id: str,
        action: str,
        resource: str,
        user_id: str | None = None,
        raise_on_deny: bool = True,
        **additional_context: Any,
    ) -> PolicyDecision:
        """
        Check if an agent can perform an action on a resource.
        
        Args:
            agent_id: The agent performing the action
            action: The action being performed
            resource: The resource being accessed
            user_id: Optional user ID for context
            raise_on_deny: Whether to raise an exception on denial
            **additional_context: Additional context for evaluation
        
        Returns:
            PolicyDecision
        
        Raises:
            PermissionError: If denied and raise_on_deny is True
        """
        decision = self.engine.evaluate_agent_access(
            agent_id=agent_id,
            action=action,
            resource=resource,
            user_id=user_id,
            additional_context=additional_context if additional_context else None,
        )

        if not decision.allowed and raise_on_deny:
            message = f"Policy denied: {', '.join(decision.denied_by)}"
            raise PermissionError(message)

        return decision

    def check_rate_limit(
        self,
        agent_id: str,
        calls_per_minute: int,
        raise_on_deny: bool = True,
    ) -> PolicyDecision:
        """
        Check if an agent has exceeded rate limits.
        
        Args:
            agent_id: The agent to check
            calls_per_minute: Current calls per minute
            raise_on_deny: Whether to raise on denial
        
        Returns:
            PolicyDecision
        """
        context = {
            "agent": {
                "id": agent_id,
                "calls_per_minute": calls_per_minute,
            },
            "action": "rate_check",
            "resource": "rate_limit",
        }

        decision = self.engine.evaluate(context, scope=PolicyScope.AGENT)

        if not decision.allowed and raise_on_deny:
            raise PermissionError(f"Rate limit exceeded: {', '.join(decision.denied_by)}")

        return decision

    def audit_action(
        self,
        agent_id: str,
        action: str,
        resource: str,
        user_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an action for audit purposes.
        
        This does not enforce any policy, it simply records the action
        in the audit log.
        """
        context = {
            "agent": {"id": agent_id},
            "action": action,
            "resource": resource,
            "user": {"id": user_id} if user_id else None,
            "details": details,
        }

        decision = self.engine.evaluate(context)
        logger.info("Audit: agent=%s action=%s resource=%s allowed=%s",
                   agent_id, action, resource, decision.allowed)


# Convenience functions
def get_agent_enforcer() -> AgentPolicyEnforcer:
    """Get an AgentPolicyEnforcer instance."""
    return AgentPolicyEnforcer()


def enforce_policy(
    agent_id: str,
    action: str,
    resource: str,
    **context: Any,
) -> PolicyDecision:
    """
    Quick helper to enforce a policy on an agent action.
    
    Raises PermissionError if denied.
    """
    return get_agent_enforcer().check(
        agent_id=agent_id,
        action=action,
        resource=resource,
        raise_on_deny=True,
        **context,
    )
