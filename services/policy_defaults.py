"""
Helix Policy Engine - Default Policy Templates
================================================

Pre-built policy templates for common use cases:
- Multi-tenant isolation
- SaaS quota management
- Agent capability restrictions
- Data classification enforcement
- GDPR compliance

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

from apps.backend.services.policy_engine import (
    Policy,
    PolicyCondition,
    PolicyEffect,
    PolicyRule,
    PolicyScope,
)


def create_multi_tenant_policies() -> list[Policy]:
    """Create policies for multi-tenant isolation."""
    policies = []

    # Tenant Data Isolation
    tenant_isolation = Policy(
        id="tenant-data-isolation",
        name="Tenant Data Isolation",
        description="Ensure users can only access their own tenant's data",
        rules=[
            PolicyRule(
                name="deny-cross-tenant-data",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="user.tenant_id", operator="exists", value=None),
                    PolicyCondition(field="resource.tenant_id", operator="neq", value="${user.tenant_id}"),
                ],
                priority=1,
                message="Cross-tenant data access denied",
            ),
            PolicyRule(
                name="audit-tenant-access",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="action", operator="eq", value="export"),
                ],
                priority=50,
                message="Data export performed",
            ),
        ],
    )
    policies.append(tenant_isolation)

    # Tenant Admin Boundaries
    tenant_admin = Policy(
        id="tenant-admin-boundaries",
        name="Tenant Admin Boundaries",
        description="Restrict tenant admin actions to their own tenant",
        rules=[
            PolicyRule(
                name="deny-cross-tenant-admin",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="user.role", operator="eq", value="tenant_admin"),
                    PolicyCondition(field="target.tenant_id", operator="neq", value="${user.tenant_id}"),
                ],
                priority=1,
                message="Tenant admins can only manage their own tenant",
            ),
        ],
    )
    policies.append(tenant_admin)

    return policies


def create_saas_quota_policies() -> list[Policy]:
    """Create policies for SaaS quota management."""
    policies = []

    # Usage Quota Enforcement
    usage_quota = Policy(
        id="saas-usage-quotas",
        name="SaaS Usage Quotas",
        description="Enforce plan-based usage limits",
        rules=[
            # Free tier limits
            PolicyRule(
                name="free-tier-api-limit",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="user.plan", operator="eq", value="free"),
                    PolicyCondition(field="user.api_calls_month", operator="gte", value=1000),
                ],
                priority=5,
                message="Free tier API limit exceeded (1000/month)",
            ),
            PolicyRule(
                name="free-tier-agent-limit",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="user.plan", operator="eq", value="free"),
                    PolicyCondition(field="user.agents_active", operator="gte", value=3),
                ],
                priority=5,
                message="Free tier allows up to 3 agents",
            ),
            # Pro tier limits
            PolicyRule(
                name="pro-tier-api-limit",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="user.plan", operator="eq", value="pro"),
                    PolicyCondition(field="user.api_calls_month", operator="gte", value=100000),
                ],
                priority=5,
                message="Pro tier API limit exceeded (100000/month)",
            ),
            PolicyRule(
                name="pro-tier-agent-limit",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="user.plan", operator="eq", value="pro"),
                    PolicyCondition(field="user.agents_active", operator="gte", value=24),
                ],
                priority=5,
                message="Pro tier allows up to 24 agents",
            ),
            # Enterprise warnings
            PolicyRule(
                name="enterprise-usage-alert",
                effect=PolicyEffect.WARN,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="user.plan", operator="eq", value="enterprise"),
                    PolicyCondition(field="user.api_calls_month", operator="gt", value=100000),
                ],
                priority=30,
                message="High API usage detected for enterprise account",
            ),
        ],
    )
    policies.append(usage_quota)

    # Feature Gating
    feature_gates = Policy(
        id="saas-feature-gates",
        name="SaaS Feature Gates",
        description="Gate features by subscription tier",
        rules=[
            PolicyRule(
                name="gate-advanced-agents",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="agent.type", operator="in", value=["system", "coordination"]),
                    PolicyCondition(field="user.plan", operator="in", value=["free", "pro"]),
                ],
                priority=5,
                message="Advanced agents require Enterprise plan",
            ),
            PolicyRule(
                name="gate-custom-integrations",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.RESOURCE,
                conditions=[
                    PolicyCondition(field="action", operator="eq", value="create_integration"),
                    PolicyCondition(field="user.plan", operator="eq", value="free"),
                ],
                priority=5,
                message="Custom integrations require Pro or Enterprise plan",
            ),
        ],
    )
    policies.append(feature_gates)

    return policies


def create_agent_capability_policies() -> list[Policy]:
    """Create policies for agent capability restrictions."""
    policies = []

    # Agent Action Boundaries
    agent_boundaries = Policy(
        id="agent-action-boundaries",
        name="Agent Action Boundaries",
        description="Define what actions agents can and cannot perform",
        rules=[
            # Prevent agents from modifying system config
            PolicyRule(
                name="deny-system-config-modification",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="action", operator="in", value=["update", "delete"]),
                    PolicyCondition(field="resource", operator="regex", value=r"^system\.config\..*"),
                ],
                priority=1,
                message="Agents cannot modify system configuration",
            ),
            # Require approval for destructive actions
            PolicyRule(
                name="audit-destructive-actions",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="action", operator="in", value=["delete", "destroy", "reset"]),
                ],
                priority=10,
                message="Destructive action performed by agent",
            ),
            # Rate limit per agent
            PolicyRule(
                name="agent-rate-limit",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="agent.calls_per_minute", operator="gt", value=100),
                ],
                priority=10,
                message="Agent rate limit exceeded (100/min)",
            ),
        ],
    )
    policies.append(agent_boundaries)

    # Agent Type Restrictions
    agent_types = Policy(
        id="agent-type-restrictions",
        name="Agent Type Restrictions",
        description="Restrict certain agent types from sensitive operations",
        rules=[
            # Sandbox agents cannot access production
            PolicyRule(
                name="sandbox-no-production",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="agent.environment", operator="eq", value="sandbox"),
                    PolicyCondition(field="resource.environment", operator="eq", value="production"),
                ],
                priority=1,
                message="Sandbox agents cannot access production resources",
            ),
            # Development agents audit production access
            PolicyRule(
                name="dev-agent-production-audit",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.AGENT,
                conditions=[
                    PolicyCondition(field="agent.environment", operator="eq", value="development"),
                    PolicyCondition(field="resource.environment", operator="eq", value="production"),
                ],
                priority=10,
                message="Development agent accessed production",
            ),
        ],
    )
    policies.append(agent_types)

    return policies


def create_data_classification_policies() -> list[Policy]:
    """Create policies for data classification enforcement."""
    policies = []

    # Data Access by Classification
    data_access = Policy(
        id="data-classification-access",
        name="Data Classification Access",
        description="Control access based on data classification level",
        rules=[
            # Public data - no restrictions
            # Internal data - require authenticated user
            PolicyRule(
                name="internal-requires-auth",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource.classification", operator="eq", value="internal"),
                    PolicyCondition(field="user.authenticated", operator="eq", value=False),
                ],
                priority=5,
                message="Internal data requires authentication",
            ),
            # Confidential data - require specific role
            PolicyRule(
                name="confidential-requires-role",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource.classification", operator="eq", value="confidential"),
                    PolicyCondition(field="user.role", operator="not_in", value=["admin", "analyst", "manager"]),
                ],
                priority=5,
                message="Confidential data requires elevated role",
            ),
            # Restricted data - require admin
            PolicyRule(
                name="restricted-requires-admin",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource.classification", operator="eq", value="restricted"),
                    PolicyCondition(field="user.role", operator="neq", value="admin"),
                ],
                priority=1,
                message="Restricted data requires admin role",
            ),
            # Audit all restricted access
            PolicyRule(
                name="audit-restricted-access",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource.classification", operator="eq", value="restricted"),
                ],
                priority=20,
                message="Restricted data accessed",
            ),
        ],
    )
    policies.append(data_access)

    # PII Protection
    pii_protection = Policy(
        id="pii-protection",
        name="PII Protection",
        description="Special handling for personally identifiable information",
        rules=[
            PolicyRule(
                name="audit-pii-access",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource.contains_pii", operator="eq", value=True),
                ],
                priority=10,
                message="PII data accessed",
            ),
            PolicyRule(
                name="deny-pii-export-non-admin",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource.contains_pii", operator="eq", value=True),
                    PolicyCondition(field="action", operator="eq", value="export"),
                    PolicyCondition(field="user.role", operator="neq", value="admin"),
                ],
                priority=5,
                message="Only admins can export PII data",
            ),
        ],
    )
    policies.append(pii_protection)

    return policies


def create_gdpr_compliance_policies() -> list[Policy]:
    """Create policies for GDPR compliance."""
    policies = []

    gdpr_policy = Policy(
        id="gdpr-compliance",
        name="GDPR Compliance",
        description="Enforce GDPR data protection requirements",
        rules=[
            # EU data subject rights
            PolicyRule(
                name="audit-eu-data-access",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource.data_subject_region", operator="eq", value="EU"),
                ],
                priority=10,
                message="EU data subject data accessed",
            ),
            # Right to erasure
            PolicyRule(
                name="audit-deletion-request",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="action", operator="eq", value="delete"),
                    PolicyCondition(field="request.type", operator="eq", value="gdpr_erasure"),
                ],
                priority=1,
                message="GDPR erasure request processed",
            ),
            # Cross-border transfer
            PolicyRule(
                name="warn-cross-border-transfer",
                effect=PolicyEffect.WARN,
                scope=PolicyScope.DATA,
                conditions=[
                    PolicyCondition(field="resource.data_subject_region", operator="eq", value="EU"),
                    PolicyCondition(field="action", operator="eq", value="transfer"),
                    PolicyCondition(field="destination.region", operator="neq", value="EU"),
                ],
                priority=10,
                message="Cross-border data transfer from EU",
            ),
        ],
    )
    policies.append(gdpr_policy)

    return policies


def create_security_policies() -> list[Policy]:
    """Create security-focused policies."""
    policies = []

    # Brute Force Protection
    brute_force = Policy(
        id="brute-force-protection",
        name="Brute Force Protection",
        description="Detect and block potential brute force attacks",
        rules=[
            PolicyRule(
                name="block-excessive-failures",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="api.endpoint", operator="eq", value="/api/auth/login"),
                    PolicyCondition(field="request.ip_failed_attempts", operator="gte", value=5),
                ],
                priority=1,
                message="Too many failed login attempts",
            ),
            PolicyRule(
                name="audit-suspicious-activity",
                effect=PolicyEffect.AUDIT,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="request.ip_failed_attempts", operator="gte", value=3),
                ],
                priority=20,
                message="Suspicious authentication activity",
            ),
        ],
    )
    policies.append(brute_force)

    # IP-based restrictions
    ip_restrictions = Policy(
        id="ip-restrictions",
        name="IP Restrictions",
        description="Block or flag requests from suspicious IPs",
        rules=[
            PolicyRule(
                name="block-blacklisted-ip",
                effect=PolicyEffect.DENY,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="request.ip_blacklisted", operator="eq", value=True),
                ],
                priority=1,
                message="Access denied from blacklisted IP",
            ),
            PolicyRule(
                name="warn-vpn-access",
                effect=PolicyEffect.WARN,
                scope=PolicyScope.API,
                conditions=[
                    PolicyCondition(field="request.ip_is_vpn", operator="eq", value=True),
                ],
                priority=30,
                message="Access via VPN detected",
            ),
        ],
    )
    policies.append(ip_restrictions)

    return policies


def load_all_default_policies() -> list[Policy]:
    """Load all default policies."""
    all_policies = []

    # Import the base defaults
    from apps.backend.services.policy_engine import create_default_policies

    all_policies.extend(create_default_policies())

    # Add domain-specific policies
    all_policies.extend(create_multi_tenant_policies())
    all_policies.extend(create_saas_quota_policies())
    all_policies.extend(create_agent_capability_policies())
    all_policies.extend(create_data_classification_policies())
    all_policies.extend(create_gdpr_compliance_policies())
    all_policies.extend(create_security_policies())

    return all_policies
