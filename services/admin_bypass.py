"""
Admin bypass re-export shim.

Canonical implementation lives in apps.backend.security.admin_bypass.
This file exists for backward compatibility with existing imports.

Author: Helix Collective
"""

from apps.backend.security.admin_bypass import (
    ADMIN_EMAILS,
    ADMIN_USER_IDS,
    AdminUser,
    UsageTracker,
    admin_bypass_middleware,
    bypass_payment,
    bypass_rate_limit,
    can_access_feature,
    check_admin_permissions,
    check_master_key,
    get_admin_action_logs,
    get_admin_dashboard_url,
    get_admin_user,
    get_effective_tier,
    is_admin_email,
    is_admin_user,
    is_admin_user_id,
    log_admin_action,
    require_admin,
    upgrade_user_to_admin,
    validate_admin_session,
)

__all__ = [
    "ADMIN_EMAILS",
    "ADMIN_USER_IDS",
    "AdminUser",
    "UsageTracker",
    "admin_bypass_middleware",
    "bypass_payment",
    "bypass_rate_limit",
    "can_access_feature",
    "check_admin_permissions",
    "check_master_key",
    "get_admin_action_logs",
    "get_admin_dashboard_url",
    "get_admin_user",
    "get_effective_tier",
    "is_admin_email",
    "is_admin_user",
    "is_admin_user_id",
    "log_admin_action",
    "require_admin",
    "upgrade_user_to_admin",
    "validate_admin_session",
]
