"""
Helix Workflow Connectors — Integration Library
=================================================

Extensible connector library for the Helix Workflow Engine.
Each connector provides node types that can be used in workflows.

Growing toward n8n's 500+ integrations, starting with the most
commonly used services.

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# CONNECTOR REGISTRY
# ============================================================================


@dataclass
class ConnectorDefinition:
    """Definition of a workflow connector."""

    id: str
    name: str
    description: str
    category: str
    icon: str
    color: str
    auth_type: str = "none"  # none, api_key, oauth2, basic
    auth_fields: list[str] = field(default_factory=list)
    node_types: list[str] = field(default_factory=list)
    documentation_url: str = ""
    version: str = "1.0.0"


_connectors: dict[str, ConnectorDefinition] = {}
_connector_handlers: dict[str, Callable] = {}


def register_connector(connector: ConnectorDefinition, handler: Callable | None = None):
    """Register a connector in the global registry."""
    _connectors[connector.id] = connector
    if handler:
        _connector_handlers[connector.id] = handler
    logger.info("Registered connector: %s (%s)", connector.name, connector.id)


def get_connector(connector_id: str) -> ConnectorDefinition | None:
    return _connectors.get(connector_id)


def list_connectors(category: str | None = None) -> list[ConnectorDefinition]:
    connectors = list(_connectors.values())
    if category:
        connectors = [c for c in connectors if c.category == category]
    return sorted(connectors, key=lambda c: c.name)


def get_connector_categories() -> list[dict[str, Any]]:
    categories: dict[str, int] = {}
    for c in _connectors.values():
        categories[c.category] = categories.get(c.category, 0) + 1
    return [{"id": k, "name": k.replace("_", " ").title(), "count": v} for k, v in sorted(categories.items())]


# ============================================================================
# CONNECTOR EXECUTION ENGINE
# ============================================================================


async def execute_connector(
    connector_id: str,
    action: str,
    params: dict[str, Any],
    credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a connector action with the given parameters."""
    connector = _connectors.get(connector_id)
    if not connector:
        return {"success": False, "error": f"Unknown connector: {connector_id}"}

    handler = _connector_handlers.get(connector_id)
    if handler:
        try:
            result = await handler(action, params, credentials or {})
            return {"success": True, "data": result}
        except Exception as e:
            logger.error("Connector %s failed: %s", connector_id, e)
            return {"success": False, "error": "Connector execution failed"}

    # Default HTTP-based execution for connectors without custom handlers
    return await _default_http_handler(connector, action, params, credentials or {})


async def _default_http_handler(
    connector: ConnectorDefinition,
    action: str,
    params: dict[str, Any],
    credentials: dict[str, str],
) -> dict[str, Any]:
    """Default HTTP handler for API-based connectors."""
    url = params.get("url", "")
    method = params.get("method", "GET").upper()
    headers = params.get("headers", {})
    body = params.get("body")

    # Apply auth
    if connector.auth_type == "api_key" and "api_key" in credentials:
        headers["Authorization"] = f"Bearer {credentials['api_key']}"
    elif connector.auth_type == "basic" and "username" in credentials:
        import base64

        creds = base64.b64encode(f"{credentials['username']}:{credentials.get('password', '')}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(method, url, headers=headers, json=body if body else None)
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
            "json": response.json() if "application/json" in response.headers.get("content-type", "") else None,
        }


# ============================================================================
# BUILT-IN CONNECTORS (40+ services)
# ============================================================================


def _register_all_connectors():
    """Register all built-in connectors."""

    # --- Communication ---
    register_connector(
        ConnectorDefinition(
            id="slack",
            name="Slack",
            description="Send messages, manage channels, and automate Slack workflows",
            category="communication",
            icon="💼",
            color="#4A154B",
            auth_type="oauth2",
            auth_fields=["bot_token", "signing_secret"],
            node_types=["slack_send_message", "slack_create_channel", "slack_upload_file", "slack_list_channels"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="discord",
            name="Discord",
            description="Send messages, manage servers, and automate Discord bots",
            category="communication",
            icon="💬",
            color="#5865F2",
            auth_type="api_key",
            auth_fields=["bot_token"],
            node_types=["discord_send_message", "discord_create_channel", "discord_add_reaction"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="telegram",
            name="Telegram",
            description="Send messages and manage Telegram bots",
            category="communication",
            icon="✈️",
            color="#0088CC",
            auth_type="api_key",
            auth_fields=["bot_token"],
            node_types=["telegram_send_message", "telegram_send_photo", "telegram_get_updates"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="email_smtp",
            name="Email (SMTP)",
            description="Send emails via SMTP with templates and attachments",
            category="communication",
            icon="📧",
            color="#EA4335",
            auth_type="basic",
            auth_fields=["smtp_host", "smtp_port", "username", "password"],
            node_types=["email_send", "email_send_template"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="twilio",
            name="Twilio",
            description="Send SMS, make calls, and manage phone numbers",
            category="communication",
            icon="📱",
            color="#F22F46",
            auth_type="api_key",
            auth_fields=["account_sid", "auth_token"],
            node_types=["twilio_send_sms", "twilio_make_call"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="sendgrid",
            name="SendGrid",
            description="Transactional and marketing email delivery",
            category="communication",
            icon="📨",
            color="#1A82E2",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["sendgrid_send_email", "sendgrid_send_template"],
        )
    )

    # --- Developer Tools ---
    register_connector(
        ConnectorDefinition(
            id="github",
            name="GitHub",
            description="Manage repos, issues, PRs, and GitHub Actions",
            category="developer_tools",
            icon="🐙",
            color="#181717",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=[
                "github_create_issue",
                "github_create_pr",
                "github_list_repos",
                "github_get_file",
                "github_create_webhook",
                "github_trigger_workflow",
            ],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="gitlab",
            name="GitLab",
            description="Manage GitLab projects, merge requests, and CI/CD",
            category="developer_tools",
            icon="🦊",
            color="#FC6D26",
            auth_type="api_key",
            auth_fields=["access_token"],
            node_types=["gitlab_create_issue", "gitlab_create_mr", "gitlab_list_projects"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="jira",
            name="Jira",
            description="Create and manage Jira issues, sprints, and boards",
            category="developer_tools",
            icon="📋",
            color="#0052CC",
            auth_type="basic",
            auth_fields=["domain", "email", "api_token"],
            node_types=["jira_create_issue", "jira_update_issue", "jira_search", "jira_add_comment"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="linear",
            name="Linear",
            description="Modern issue tracking and project management",
            category="developer_tools",
            icon="🔷",
            color="#5E6AD2",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["linear_create_issue", "linear_update_issue", "linear_list_issues"],
        )
    )

    # --- Cloud & Infrastructure ---
    register_connector(
        ConnectorDefinition(
            id="aws_s3",
            name="AWS S3",
            description="Upload, download, and manage files in S3 buckets",
            category="cloud",
            icon="☁️",
            color="#FF9900",
            auth_type="api_key",
            auth_fields=["access_key_id", "secret_access_key", "region"],
            node_types=["s3_upload", "s3_download", "s3_list_objects", "s3_delete"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="gcp_storage",
            name="Google Cloud Storage",
            description="Manage files in GCS buckets",
            category="cloud",
            icon="🌐",
            color="#4285F4",
            auth_type="api_key",
            auth_fields=["service_account_json"],
            node_types=["gcs_upload", "gcs_download", "gcs_list"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="cloudflare",
            name="Cloudflare",
            description="Manage DNS, Workers, and CDN settings",
            category="cloud",
            icon="🛡️",
            color="#F38020",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["cloudflare_purge_cache", "cloudflare_create_dns", "cloudflare_list_zones"],
        )
    )

    # --- Databases ---
    register_connector(
        ConnectorDefinition(
            id="postgresql",
            name="PostgreSQL",
            description="Query and manage PostgreSQL databases",
            category="databases",
            icon="🐘",
            color="#336791",
            auth_type="basic",
            auth_fields=["host", "port", "database", "username", "password"],
            node_types=["pg_query", "pg_insert", "pg_update", "pg_delete"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="mysql",
            name="MySQL",
            description="Query and manage MySQL databases",
            category="databases",
            icon="🐬",
            color="#4479A1",
            auth_type="basic",
            auth_fields=["host", "port", "database", "username", "password"],
            node_types=["mysql_query", "mysql_insert", "mysql_update"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="mongodb",
            name="MongoDB",
            description="Query and manage MongoDB collections",
            category="databases",
            icon="🍃",
            color="#47A248",
            auth_type="basic",
            auth_fields=["connection_string"],
            node_types=["mongo_find", "mongo_insert", "mongo_update", "mongo_aggregate"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="redis",
            name="Redis",
            description="Cache operations and pub/sub messaging",
            category="databases",
            icon="🔴",
            color="#DC382D",
            auth_type="basic",
            auth_fields=["url"],
            node_types=["redis_get", "redis_set", "redis_publish", "redis_subscribe"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="supabase",
            name="Supabase",
            description="Supabase database, auth, and storage",
            category="databases",
            icon="⚡",
            color="#3ECF8E",
            auth_type="api_key",
            auth_fields=["url", "anon_key", "service_role_key"],
            node_types=["supabase_query", "supabase_insert", "supabase_rpc"],
        )
    )

    # --- AI & ML ---
    register_connector(
        ConnectorDefinition(
            id="openai",
            name="OpenAI",
            description="GPT-4, DALL-E, Whisper, and Embeddings",
            category="ai_ml",
            icon="🤖",
            color="#412991",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["openai_chat", "openai_completion", "openai_embedding", "openai_image", "openai_whisper"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="anthropic",
            name="Anthropic",
            description="Claude models for text generation and analysis",
            category="ai_ml",
            icon="🧠",
            color="#D97706",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["anthropic_chat", "anthropic_completion"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="google_ai",
            name="Google AI (Gemini)",
            description="Gemini models for multimodal AI",
            category="ai_ml",
            icon="✨",
            color="#4285F4",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["gemini_chat", "gemini_vision"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="huggingface",
            name="Hugging Face",
            description="Access thousands of ML models",
            category="ai_ml",
            icon="🤗",
            color="#FFD21E",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["hf_inference", "hf_embedding", "hf_classification"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="replicate",
            name="Replicate",
            description="Run ML models in the cloud",
            category="ai_ml",
            icon="🔄",
            color="#000000",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["replicate_run", "replicate_predict"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="helix_llm",
            name="Helix LLM",
            description="Proprietary Helix coordination-aware LLM",
            category="ai_ml",
            icon="🌌",
            color="#6D28D9",
            auth_type="none",
            auth_fields=[],
            node_types=["helix_generate", "helix_stream", "helix_agent_call"],
        )
    )

    # --- Productivity ---
    register_connector(
        ConnectorDefinition(
            id="notion",
            name="Notion",
            description="Create and manage Notion pages, databases, and blocks",
            category="productivity",
            icon="📝",
            color="#000000",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["notion_create_page", "notion_query_database", "notion_update_page", "notion_append_block"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="google_sheets",
            name="Google Sheets",
            description="Read, write, and manage spreadsheets",
            category="productivity",
            icon="📊",
            color="#34A853",
            auth_type="oauth2",
            auth_fields=["credentials_json"],
            node_types=["sheets_read", "sheets_write", "sheets_append", "sheets_create"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="google_drive",
            name="Google Drive",
            description="Upload, download, and manage files",
            category="productivity",
            icon="📁",
            color="#4285F4",
            auth_type="oauth2",
            auth_fields=["credentials_json"],
            node_types=["drive_upload", "drive_download", "drive_list", "drive_create_folder"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="google_calendar",
            name="Google Calendar",
            description="Create and manage calendar events",
            category="productivity",
            icon="📅",
            color="#4285F4",
            auth_type="oauth2",
            auth_fields=["credentials_json"],
            node_types=["calendar_create_event", "calendar_list_events", "calendar_update_event"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="airtable",
            name="Airtable",
            description="Manage Airtable bases, tables, and records",
            category="productivity",
            icon="📋",
            color="#18BFFF",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["airtable_list", "airtable_create", "airtable_update", "airtable_delete"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="trello",
            name="Trello",
            description="Manage Trello boards, lists, and cards",
            category="productivity",
            icon="📌",
            color="#0079BF",
            auth_type="api_key",
            auth_fields=["api_key", "token"],
            node_types=["trello_create_card", "trello_move_card", "trello_list_boards"],
        )
    )

    # --- Marketing & CRM ---
    register_connector(
        ConnectorDefinition(
            id="hubspot",
            name="HubSpot",
            description="CRM, marketing, and sales automation",
            category="marketing_crm",
            icon="🧲",
            color="#FF7A59",
            auth_type="api_key",
            auth_fields=["access_token"],
            node_types=["hubspot_create_contact", "hubspot_create_deal", "hubspot_search", "hubspot_update_contact"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="salesforce",
            name="Salesforce",
            description="CRM operations and data management",
            category="marketing_crm",
            icon="☁️",
            color="#00A1E0",
            auth_type="oauth2",
            auth_fields=["instance_url", "access_token"],
            node_types=["sf_query", "sf_create", "sf_update", "sf_delete"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="mailchimp",
            name="Mailchimp",
            description="Email marketing campaigns and audience management",
            category="marketing_crm",
            icon="🐵",
            color="#FFE01B",
            auth_type="api_key",
            auth_fields=["api_key", "server_prefix"],
            node_types=["mailchimp_add_subscriber", "mailchimp_send_campaign", "mailchimp_list_audiences"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="stripe",
            name="Stripe",
            description="Payment processing, subscriptions, and invoicing",
            category="marketing_crm",
            icon="💳",
            color="#635BFF",
            auth_type="api_key",
            auth_fields=["secret_key"],
            node_types=[
                "stripe_create_charge",
                "stripe_create_customer",
                "stripe_list_invoices",
                "stripe_create_subscription",
            ],
        )
    )

    # --- Social Media ---
    register_connector(
        ConnectorDefinition(
            id="twitter",
            name="Twitter/X",
            description="Post tweets, manage followers, and search",
            category="social_media",
            icon="🐦",
            color="#1DA1F2",
            auth_type="oauth2",
            auth_fields=["api_key", "api_secret", "access_token", "access_secret"],
            node_types=["twitter_post", "twitter_search", "twitter_get_user"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="linkedin",
            name="LinkedIn",
            description="Post updates and manage company pages",
            category="social_media",
            icon="💼",
            color="#0A66C2",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["linkedin_post", "linkedin_get_profile"],
        )
    )

    # --- Monitoring & Analytics ---
    register_connector(
        ConnectorDefinition(
            id="datadog",
            name="Datadog",
            description="Monitoring, alerting, and log management",
            category="monitoring",
            icon="🐕",
            color="#632CA6",
            auth_type="api_key",
            auth_fields=["api_key", "app_key"],
            node_types=["datadog_send_metric", "datadog_create_event", "datadog_query_metrics"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="pagerduty",
            name="PagerDuty",
            description="Incident management and alerting",
            category="monitoring",
            icon="🚨",
            color="#06AC38",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["pagerduty_create_incident", "pagerduty_resolve_incident"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="sentry",
            name="Sentry",
            description="Error tracking and performance monitoring",
            category="monitoring",
            icon="🐛",
            color="#362D59",
            auth_type="api_key",
            auth_fields=["dsn", "auth_token"],
            node_types=["sentry_capture_event", "sentry_list_issues"],
        )
    )

    # --- Storage & Files ---
    register_connector(
        ConnectorDefinition(
            id="dropbox",
            name="Dropbox",
            description="File storage and sharing",
            category="storage",
            icon="📦",
            color="#0061FF",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["dropbox_upload", "dropbox_download", "dropbox_list"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="backblaze_b2",
            name="Backblaze B2",
            description="Affordable cloud object storage",
            category="storage",
            icon="🔵",
            color="#E21E29",
            auth_type="api_key",
            auth_fields=["application_key_id", "application_key"],
            node_types=["b2_upload", "b2_download", "b2_list"],
        )
    )

    # --- Webhooks & HTTP ---
    register_connector(
        ConnectorDefinition(
            id="webhook",
            name="Webhook",
            description="Send and receive HTTP webhooks",
            category="core",
            icon="🔗",
            color="#10B981",
            auth_type="none",
            auth_fields=[],
            node_types=["webhook_trigger", "webhook_send", "webhook_respond"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="http",
            name="HTTP Request",
            description="Make arbitrary HTTP requests to any API",
            category="core",
            icon="🌐",
            color="#3B82F6",
            auth_type="none",
            auth_fields=[],
            node_types=["http_get", "http_post", "http_put", "http_delete", "http_patch"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="graphql",
            name="GraphQL",
            description="Execute GraphQL queries and mutations",
            category="core",
            icon="◈",
            color="#E535AB",
            auth_type="api_key",
            auth_fields=["endpoint", "api_key"],
            node_types=["graphql_query", "graphql_mutation"],
        )
    )

    # --- Developer Tools (Expanded) ---
    register_connector(
        ConnectorDefinition(
            id="gitlab",
            name="GitLab",
            description="GitLab CI/CD, repositories, and issues",
            category="developer_tools",
            icon="🦊",
            color="#FC6D26",
            auth_type="api_key",
            auth_fields=["access_token"],
            node_types=["gitlab_list_projects", "gitlab_create_issue", "gitlab_trigger_pipeline", "gitlab_get_file"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="bitbucket",
            name="Bitbucket",
            description="Bitbucket repositories and pull requests",
            category="developer_tools",
            icon="🐦",
            color="#0052CC",
            auth_type="api_key",
            auth_fields=["username", "app_password"],
            node_types=["bitbucket_list_repos", "bitbucket_create_pr", "bitbucket_get_branches"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="vercel",
            name="Vercel",
            description="Vercel deployments and projects",
            category="developer_tools",
            icon="▲",
            color="#000000",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["vercel_list_deployments", "vercel_create_deployment", "vercel_get_project"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="netlify",
            name="Netlify",
            description="Netlify deployments and sites",
            category="developer_tools",
            icon="🚀",
            color="#00C7B7",
            auth_type="api_key",
            auth_fields=["access_token"],
            node_types=["netlify_list_sites", "netlify_create_deploy", "netlify_get_deploy_logs"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="heroku",
            name="Heroku",
            description="Heroku app management and deployments",
            category="developer_tools",
            icon="🔷",
            color="#430098",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["heroku_list_apps", "heroku_create_app", "heroku_restart_dyno"],
        )
    )

    # --- Cloud Providers ---
    register_connector(
        ConnectorDefinition(
            id="aws_s3",
            name="AWS S3",
            description="Amazon S3 storage operations",
            category="cloud",
            icon="☁️",
            color="#FF9900",
            auth_type="api_key",
            auth_fields=["access_key_id", "secret_access_key", "region"],
            node_types=["s3_upload", "s3_download", "s3_list", "s3_delete", "s3_get_url"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="aws_ses",
            name="AWS SES",
            description="Amazon SES email sending",
            category="cloud",
            icon="📧",
            color="#FF9900",
            auth_type="api_key",
            auth_fields=["access_key_id", "secret_access_key", "region"],
            node_types=["ses_send_email", "ses_verify_email", "ses_get_statistics"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="azure_storage",
            name="Azure Storage",
            description="Azure Blob storage operations",
            category="cloud",
            icon="🔷",
            color="#0078D4",
            auth_type="api_key",
            auth_fields=["account_name", "account_key"],
            node_types=["azure_upload", "azure_download", "azure_list_blobs"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="gcp_storage",
            name="Google Cloud Storage",
            description="GCS bucket operations",
            category="cloud",
            icon="🌐",
            color="#4285F4",
            auth_type="oauth2",
            auth_fields=["credentials_json"],
            node_types=["gcs_upload", "gcs_download", "gcs_list", "gcs_delete"],
        )
    )

    # --- Databases (Expanded) ---
    register_connector(
        ConnectorDefinition(
            id="mongodb",
            name="MongoDB",
            description="MongoDB database operations",
            category="database",
            icon="🍃",
            color="#47A248",
            auth_type="api_key",
            auth_fields=["connection_string", "database"],
            node_types=["mongodb_find", "mongodb_insert", "mongodb_update", "mongodb_delete", "mongodb_aggregate"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="redis",
            name="Redis",
            description="Redis cache operations",
            category="database",
            icon="🔴",
            color="#DC382D",
            auth_type="api_key",
            auth_fields=["host", "port", "password"],
            node_types=["redis_get", "redis_set", "redis_delete", "redis_keys", "redis_incr"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="elasticsearch",
            name="Elasticsearch",
            description="Elasticsearch search operations",
            category="database",
            icon="🔍",
            color="#FEC514",
            auth_type="api_key",
            auth_fields=["url", "username", "password"],
            node_types=["es_search", "es_index", "es_update", "es_delete", "es_bulk"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="firebase",
            name="Firebase",
            description="Firebase realtime database and auth",
            category="database",
            icon="🔥",
            color="#FFCA28",
            auth_type="api_key",
            auth_fields=["api_key", "project_id"],
            node_types=["firebase_get", "firebase_set", "firebase_update", "firebase_delete"],
        )
    )

    # --- Communication (Expanded) ---
    register_connector(
        ConnectorDefinition(
            id="msteams",
            name="Microsoft Teams",
            description="Teams messages and channels",
            category="communication",
            icon="👥",
            color="#6264A7",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["teams_send_message", "teams_list_channels", "teams_create_channel"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="telegram",
            name="Telegram",
            description="Telegram bot messages",
            category="communication",
            icon="✈️",
            color="#0088CC",
            auth_type="api_key",
            auth_fields=["bot_token"],
            node_types=["telegram_send_message", "telegram_send_photo", "telegram_get_updates"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="twilio",
            name="Twilio",
            description="SMS and voice calls",
            category="communication",
            icon="📱",
            color="#F22F46",
            auth_type="api_key",
            auth_fields=["account_sid", "auth_token"],
            node_types=["twilio_send_sms", "twilio_make_call", "twilio_lookup_number"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="sendgrid",
            name="SendGrid",
            description="Transactional email delivery",
            category="communication",
            icon="📨",
            color="#0078FF",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["sendgrid_send", "sendgrid_template", "sendgrid_stats"],
        )
    )

    # --- E-Commerce ---
    register_connector(
        ConnectorDefinition(
            id="shopify",
            name="Shopify",
            description="Shopify store management",
            category="ecommerce",
            icon="🛍️",
            color="#96BF48",
            auth_type="api_key",
            auth_fields=["api_key", "password", "store_name"],
            node_types=[
                "shopify_get_products",
                "shopify_create_order",
                "shopify_update_product",
                "shopify_get_customers",
            ],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="woocommerce",
            name="WooCommerce",
            description="WooCommerce store operations",
            category="ecommerce",
            icon="🏪",
            color="#96588A",
            auth_type="api_key",
            auth_fields=["consumer_key", "consumer_secret", "store_url"],
            node_types=["wc_get_orders", "wc_get_products", "wc_update_order", "wc_create_coupon"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="bigcommerce",
            name="BigCommerce",
            description="BigCommerce store management",
            category="ecommerce",
            icon="🏪",
            color="#121212",
            auth_type="api_key",
            auth_fields=["access_token", "store_hash"],
            node_types=["bc_get_products", "bc_get_orders", "bc_update_product"],
        )
    )

    # --- Customer Support ---
    register_connector(
        ConnectorDefinition(
            id="zendesk",
            name="Zendesk",
            description="Zendesk support tickets",
            category="support",
            icon="🎫",
            color="#03363D",
            auth_type="api_key",
            auth_fields=["subdomain", "email", "api_token"],
            node_types=[
                "zendesk_list_tickets",
                "zendesk_create_ticket",
                "zendesk_update_ticket",
                "zendesk_get_comments",
            ],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="intercom",
            name="Intercom",
            description="Intercom customer messaging",
            category="support",
            icon="💬",
            color="#1F8DED",
            auth_type="api_key",
            auth_fields=["access_token"],
            node_types=["intercom_list_users", "intercom_send_message", "intercom_create_user"],
        )
    )

    # --- Project Management ---
    register_connector(
        ConnectorDefinition(
            id="asana",
            name="Asana",
            description="Asana tasks and projects",
            category="project_management",
            icon="📋",
            color="#27334D",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["asana_list_tasks", "asana_create_task", "asana_update_task", "asana_list_projects"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="monday",
            name="Monday.com",
            description="Monday.com boards and items",
            category="project_management",
            icon="📅",
            color="#0073B1",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["monday_list_items", "monday_create_item", "monday_update_item"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="notion",
            name="Notion",
            description="Notion pages and databases",
            category="productivity",
            icon="📝",
            color="#000000",
            auth_type="api_key",
            auth_fields=["integration_token"],
            node_types=["notion_search", "notion_create_page", "notion_update_page", "notion_query_database"],
        )
    )

    # --- Finance ---
    register_connector(
        ConnectorDefinition(
            id="paypal",
            name="PayPal",
            description="PayPal payments and transactions",
            category="finance",
            icon="💰",
            color="#00457C",
            auth_type="api_key",
            auth_fields=["client_id", "client_secret"],
            node_types=["paypal_create_order", "paypal_capture_order", "paypal_get_transaction"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="square",
            name="Square",
            description="Square payments and catalogs",
            category="finance",
            icon="⬜",
            color="#006AFF",
            auth_type="api_key",
            auth_fields=["access_token"],
            node_types=["square_create_payment", "square_list_catalog", "square_create_customer"],
        )
    )

    # --- AI & ML ---
    register_connector(
        ConnectorDefinition(
            id="openai",
            name="OpenAI",
            description="GPT and DALL-E AI services",
            category="ai_ml",
            icon="🤖",
            color="#10A37F",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["openai_chat", "openai_image", "openai_embedding", "openai_transcribe"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="anthropic",
            name="Anthropic",
            description="Claude AI services",
            category="ai_ml",
            icon="🧠",
            color="#CC785C",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["anthropic_chat", "anthropic_message"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="huggingface",
            name="HuggingFace",
            description="HuggingFace models and datasets",
            category="ai_ml",
            icon="🤗",
            color="#FFD21E",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["hf_inference", "hf_list_models", "hf_download_model"],
        )
    )

    # --- Analytics ---
    register_connector(
        ConnectorDefinition(
            id="google_analytics",
            name="Google Analytics",
            description="GA4 analytics data",
            category="analytics",
            icon="📊",
            color="#F9AB00",
            auth_type="oauth2",
            auth_fields=["credentials_json"],
            node_types=["ga_get_report", "ga_list_properties", "ga_get_events"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="mixpanel",
            name="Mixpanel",
            description="Mixpanel event tracking",
            category="analytics",
            icon="🎵",
            color="#A02B2D",
            auth_type="api_key",
            auth_fields=["api_secret", "project_token"],
            node_types=["mixpanel_track", "mixpanel_query", "mixpanel_export"],
        )
    )

    # --- Security ---
    register_connector(
        ConnectorDefinition(
            id="auth0",
            name="Auth0",
            description="Auth0 authentication",
            category="security",
            icon="🔐",
            color="#EB5424",
            auth_type="api_key",
            auth_fields=["domain", "client_id", "client_secret"],
            node_types=["auth0_get_user", "auth0_create_user", "auth0_update_user"],
        )
    )

    # --- Marketing ---
    register_connector(
        ConnectorDefinition(
            id="google_ads",
            name="Google Ads",
            description="Google Ads management",
            category="marketing",
            icon="📢",
            color="#4285F4",
            auth_type="oauth2",
            auth_fields=["credentials_json"],
            node_types=["google_ads_list_campaigns", "google_ads_create_ad", "google_ads_get_stats"],
        )
    )

    # --- Content Management ---
    register_connector(
        ConnectorDefinition(
            id="wordpress",
            name="WordPress",
            description="WordPress posts and pages",
            category="cms",
            icon="📝",
            color="#21759B",
            auth_type="api_key",
            auth_fields=["username", "password", "site_url"],
            node_types=["wp_list_posts", "wp_create_post", "wp_update_post", "wp_get_media"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="contentful",
            name="Contentful",
            description="Contentful CMS operations",
            category="cms",
            icon="📄",
            color="#2478BA",
            auth_type="api_key",
            auth_fields=["space_id", "access_token"],
            node_types=["contentful_list_entries", "contentful_create_entry", "contentful_update_entry"],
        )
    )

    # --- More Integrations ---
    register_connector(
        ConnectorDefinition(
            id="typeform",
            name="Typeform",
            description="Typeform surveys and responses",
            category="productivity",
            icon="📋",
            color="#191919",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["typeform_list_forms", "typeform_get_responses", "typeform_create_form"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="calendly",
            name="Calendly",
            description="Calendly scheduling",
            category="productivity",
            icon="📅",
            color="#006BFF",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["calendly_list_events", "calendly_create_event", "calendly_get_user"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="figma",
            name="Figma",
            description="Figma design files",
            category="developer_tools",
            icon="🎨",
            color="#F24E1E",
            auth_type="api_key",
            auth_fields=["access_token"],
            node_types=["figma_get_file", "figma_list_comments", "figma_create_comment"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="linear",
            name="Linear",
            description="Linear issue tracking",
            category="project_management",
            icon="⚡",
            color="#5E6AD2",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["linear_list_issues", "linear_create_issue", "linear_update_issue"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="todoist",
            name="Todoist",
            description="Todoist task management",
            category="productivity",
            icon="✅",
            color="#E44332",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["todoist_list_tasks", "todoist_create_task", "todoist_complete_task"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="clickup",
            name="ClickUp",
            description="ClickUp tasks and spaces",
            category="project_management",
            icon="🚀",
            color="#7B68EE",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["clickup_list_tasks", "clickup_create_task", "clickup_get_team"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="confluence",
            name="Confluence",
            description="Confluence pages and spaces",
            category="productivity",
            icon="📘",
            color="#0052CC",
            auth_type="api_key",
            auth_fields=["username", "api_token"],
            node_types=["confluence_get_page", "confluence_create_page", "confluence_update_page"],
        )
    )

    # --- Additional Developer Tools ---
    register_connector(
        ConnectorDefinition(
            id="jenkins",
            name="Jenkins",
            description="Jenkins CI/CD builds and jobs",
            category="developer_tools",
            icon="⚙️",
            color="#D33833",
            auth_type="api_key",
            auth_fields=["username", "api_token", "server_url"],
            node_types=["jenkins_build_job", "jenkins_get_build_status", "jenkins_list_jobs"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="circleci",
            name="CircleCI",
            description="CircleCI pipelines and workflows",
            category="developer_tools",
            icon="⭕",
            color="#343434",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["circleci_trigger_pipeline", "circleci_get_pipeline", "circleci_list_workflows"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="travisci",
            name="Travis CI",
            description="Travis CI build status and logs",
            category="developer_tools",
            icon="🚃",
            color="#CD201F",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["travis_trigger_build", "travis_get_build", "travis_get_logs"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="snyk",
            name="Snyk",
            description="Security vulnerability scanning",
            category="developer_tools",
            icon="🛡️",
            color="#812CE5",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["snyk_test_project", "snyk_scan_dependencies", "snyk_get_vulnerabilities"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="sonarqube",
            name="SonarQube",
            description="Code quality analysis",
            category="developer_tools",
            icon="🔊",
            color="#4E9BCD",
            auth_type="api_key",
            auth_fields=["token", "server_url"],
            node_types=["sonar_scan_project", "sonar_get_issues", "sonar_get_measures"],
        )
    )

    # --- Additional Cloud & Infrastructure ---
    register_connector(
        ConnectorDefinition(
            id="aws_lambda",
            name="AWS Lambda",
            description="AWS Lambda function management",
            category="cloud",
            icon="⚡",
            color="#FF9900",
            auth_type="api_key",
            auth_fields=["access_key_id", "secret_access_key", "region"],
            node_types=["lambda_invoke", "lambda_list_functions", "lambda_create_function"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="aws_ec2",
            name="AWS EC2",
            description="AWS EC2 instance management",
            category="cloud",
            icon="🖥️",
            color="#FF9900",
            auth_type="api_key",
            auth_fields=["access_key_id", "secret_access_key", "region"],
            node_types=["ec2_start_instance", "ec2_stop_instance", "ec2_list_instances"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="aws_sqs",
            name="AWS SQS",
            description="AWS SQS message queues",
            category="cloud",
            icon="📨",
            color="#FF9900",
            auth_type="api_key",
            auth_fields=["access_key_id", "secret_access_key", "region"],
            node_types=["sqs_send_message", "sqs_receive_message", "sqs_list_queues"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="azure_functions",
            name="Azure Functions",
            description="Azure function management",
            category="cloud",
            icon="⚡",
            color="#0078D4",
            auth_type="oauth2",
            auth_fields=["credentials_json"],
            node_types=["azure_invoke_function", "azure_list_functions", "azure_get_logs"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="gcp_cloudfunctions",
            name="Google Cloud Functions",
            description="GCP function deployment and invocation",
            category="cloud",
            icon="☁️",
            color="#4285F4",
            auth_type="oauth2",
            auth_fields=["credentials_json"],
            node_types=["gcf_invoke", "gcf_list_functions", "gcf_deploy"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="digitalocean",
            name="DigitalOcean",
            description="DigitalOcean droplet management",
            category="cloud",
            icon="🌊",
            color="#0069FF",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["do_list_droplets", "do_create_droplet", "do_delete_droplet"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="linode",
            name="Linode",
            description="Linode instance management",
            category="cloud",
            icon="🌲",
            color="#00B159",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["linode_list_instances", "linode_reboot", "linode_get_instance"],
        )
    )

    # --- Additional Communication ---
    register_connector(
        ConnectorDefinition(
            id="mattermost",
            name="Mattermost",
            description="Mattermost team messaging",
            category="communication",
            icon="💬",
            color="#0078C8",
            auth_type="api_key",
            auth_fields=["url", "api_token"],
            node_types=["mattermost_send_message", "mattermost_list_channels", "mattermost_create_post"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="rocketchat",
            name="Rocket.Chat",
            description="Rocket.Chat messaging",
            category="communication",
            icon="🚀",
            color="#CC2E6C",
            auth_type="api_key",
            auth_fields=["url", "auth_token", "user_id"],
            node_types=["rc_send_message", "rc_list_channels", "rc_get_user"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="victorops",
            name="VictorOps",
            description="VictorOps incident management",
            category="communication",
            icon="🚨",
            color="#005578",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["victorops_alert", "victorops_escalate"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="opsgenie",
            name="Opsgenie",
            description="Opsgenie alert management",
            category="communication",
            icon="📢",
            color="#434343",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["opsgenie_alert", "opsgenie_list_alerts", "opsgenie_close_alert"],
        )
    )

    # --- Additional E-Commerce ---
    register_connector(
        ConnectorDefinition(
            id="magento",
            name="Magento",
            description="Magento store operations",
            category="ecommerce",
            icon="🛒",
            color="#F26322",
            auth_type="api_key",
            auth_fields=["api_key", "api_secret", "store_url"],
            node_types=["magento_get_products", "magento_create_order", "magento_get_customers"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="etsy",
            name="Etsy",
            description="Etsy shop management",
            category="ecommerce",
            icon="🧶",
            color="#F56400",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["etsy_get_listings", "etsy_update_listing", "etsy_get_orders"],
        )
    )

    # --- Additional CRM & Sales ---
    register_connector(
        ConnectorDefinition(
            id="pipedrive",
            name="Pipedrive",
            description="Pipedrive CRM deals and contacts",
            category="marketing_crm",
            icon="🚀",
            color="#005A9C",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["pipedrive_deals", "pipedrive_contacts", "pipedrive_activities"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="zoho_crm",
            name="Zoho CRM",
            description="Zoho CRM operations",
            category="marketing_crm",
            icon="📊",
            color="#064F8C",
            auth_type="api_key",
            auth_fields=["client_id", "client_secret", "refresh_token"],
            node_types=["zoho_leads", "zoho_contacts", "zoho_deals"],
        )
    )

    # --- Additional Marketing ---
    register_connector(
        ConnectorDefinition(
            id="mailgun",
            name="Mailgun",
            description="Transactional email delivery",
            category="marketing_crm",
            icon="✉️",
            color="#F45A25",
            auth_type="api_key",
            auth_fields=["api_key", "domain"],
            node_types=["mailgun_send", "mailgun_stats", "mailgun_validate_email"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="sendinblue",
            name="Sendinblue",
            description="Email marketing and campaigns",
            category="marketing_crm",
            icon="📧",
            color="#2D7FF9",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["sendinblue_email", "sendinblue_contacts", "sendinblue_campaigns"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="activecampaign",
            name="ActiveCampaign",
            description="Email marketing automation",
            category="marketing",
            icon="📨",
            color="#FFC20E",
            auth_type="api_key",
            auth_fields=["api_key", "api_url"],
            node_types=["ac_contacts", "ac_campaigns", "ac_automations"],
        )
    )

    # --- Additional Social Media ---
    register_connector(
        ConnectorDefinition(
            id="facebook",
            name="Facebook",
            description="Facebook pages and posts",
            category="social_media",
            icon="👍",
            color="#1877F2",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["facebook_post", "facebook_get_page", "facebook_get_insights"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="instagram",
            name="Instagram",
            description="Instagram media and posts",
            category="social_media",
            icon="📷",
            color="#E1306C",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["instagram_post", "instagram_get_media", "instagram_get_comments"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="reddit",
            name="Reddit",
            description="Reddit posts and comments",
            category="social_media",
            icon="🤖",
            color="#FF4500",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["reddit_post", "reddit_get_subreddit", "reddit_get_comments"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="youtube",
            name="YouTube",
            description="YouTube video management",
            category="social_media",
            icon="📺",
            color="#FF0000",
            auth_type="oauth2",
            auth_fields=["access_token"],
            node_types=["youtube_upload", "youtube_list_videos", "youtube_get_comments"],
        )
    )

    # --- Additional Support ---
    register_connector(
        ConnectorDefinition(
            id="freshdesk",
            name="Freshdesk",
            description="Freshdesk support tickets",
            category="support",
            icon="🎫",
            color="#3C425A",
            auth_type="api_key",
            auth_fields=["api_key", "domain"],
            node_types=["freshdesk_tickets", "freshdesk_create_ticket", "freshdesk_update_ticket"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="helpscout",
            name="HelpScout",
            description="HelpScout conversations",
            category="support",
            icon="📬",
            color="#339877",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["helpscout_conversations", "helpscout_mailbox", "helpscout_users"],
        )
    )

    # --- Additional Analytics ---
    register_connector(
        ConnectorDefinition(
            id="amplitude",
            name="Amplitude",
            description="Amplitude analytics",
            category="analytics",
            icon="📈",
            color="#5A3D8B",
            auth_type="api_key",
            auth_fields=["api_key", "secret_key"],
            node_types=["amplitude_event", "amplitude_user", "amplitude_cohorts"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="segment",
            name="Segment",
            description="Segment data pipeline",
            category="analytics",
            icon="📊",
            color="#5F5CFF",
            auth_type="api_key",
            auth_fields=["write_key"],
            node_types=["segment_track", "segment_identify", "segment_group"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="hotjar",
            name="Hotjar",
            description="Hotjar heatmaps and recordings",
            category="analytics",
            icon="🔥",
            color="#FF3C00",
            auth_type="api_key",
            auth_fields=["site_id"],
            node_types=["hotjar_recordings", "hotjar_heatmaps", "hotjar_feedback"],
        )
    )

    # --- Additional Security ---
    register_connector(
        ConnectorDefinition(
            id="okta",
            name="Okta",
            description="Okta identity management",
            category="security",
            icon="🔐",
            color="#007DC1",
            auth_type="api_key",
            auth_fields=["api_token", "domain"],
            node_types=["okta_users", "okta_groups", "okta_applications"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="onelogin",
            name="OneLogin",
            description="OneLogin SSO",
            category="security",
            icon="1️⃣",
            color="#009FE3",
            auth_type="api_key",
            auth_fields=["client_id", "client_secret"],
            node_types=["onelogin_users", "onelogin_apps"],
        )
    )

    # --- Additional Finance ---
    register_connector(
        ConnectorDefinition(
            id="stripe_connect",
            name="Stripe Connect",
            description="Stripe Connect marketplace",
            category="finance",
            icon="💳",
            color="#635BFF",
            auth_type="api_key",
            auth_fields=["secret_key", "platform_account"],
            node_types=["stripe_connect_account", "stripe_connect_transfer", "stripe_connect_balance"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="braintree",
            name="Braintree",
            description="Braintree payments",
            category="finance",
            icon="💵",
            color="#3498DB",
            auth_type="api_key",
            auth_fields=["merchant_id", "public_key", "private_key"],
            node_types=["braintree_sale", "braintree_customer", "braintree_transaction"],
        )
    )

    # --- Additional Content Management ---
    register_connector(
        ConnectorDefinition(
            id="drupal",
            name="Drupal",
            description="Drupal content management",
            category="cms",
            icon="💧",
            color="#0678BE",
            auth_type="api_key",
            auth_fields=["username", "password", "site_url"],
            node_types=["drupal_nodes", "drupal_create_content", "drupal_taxonomy"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="ghost",
            name="Ghost",
            description="Ghost blogging platform",
            category="cms",
            icon="👻",
            color="#738a96",
            auth_type="api_key",
            auth_fields=["api_url", "api_key"],
            node_types=["ghost_posts", "ghost_create_post", "ghost_pages"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="strapi",
            name="Strapi",
            description="Strapi headless CMS",
            category="cms",
            icon="🐙",
            color="#2E7EEA",
            auth_type="api_key",
            auth_fields=["api_url", "api_token"],
            node_types=["strapi_entries", "strapi_create", "strapi_update"],
        )
    )

    # --- Additional AI/ML ---
    register_connector(
        ConnectorDefinition(
            id="replicate",
            name="Replicate",
            description="Replicate AI models",
            category="ai_ml",
            icon="🔄",
            color="#E00",
            auth_type="api_key",
            auth_fields=["api_token"],
            node_types=["replicate_run", "replicate_predictions", "replicate_models"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="cohere",
            name="Cohere",
            description="Cohere NLP models",
            category="ai_ml",
            icon="💬",
            color="#395FFD",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["cohere_generate", "cohere_embed", "cohere_classify"],
        )
    )
    register_connector(
        ConnectorDefinition(
            id="stability_ai",
            name="Stability AI",
            description="Stability AI image generation",
            category="ai_ml",
            icon="🎨",
            color="#008080",
            auth_type="api_key",
            auth_fields=["api_key"],
            node_types=["stability_generate", "stability_upscale", "stability_edit"],
        )
    )

    logger.info(
        "Registered %d connectors with %d total node types",
        len(_connectors),
        sum(len(c.node_types) for c in _connectors.values()),
    )


# Auto-register on import
_register_all_connectors()


# ============================================================================
# API ROUTES
# ============================================================================

from fastapi import APIRouter, HTTPException, Query  # noqa: E402
from pydantic import BaseModel  # noqa: E402

router = APIRouter(prefix="/api/connectors", tags=["Workflow Connectors"])


@router.get("/")
async def list_all_connectors(category: str | None = Query(None)):
    """List all available connectors."""
    connectors = list_connectors(category)
    return {
        "connectors": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "category": c.category,
                "icon": c.icon,
                "color": c.color,
                "auth_type": c.auth_type,
                "node_types": c.node_types,
                "node_count": len(c.node_types),
                "version": c.version,
            }
            for c in connectors
        ],
        "total": len(connectors),
        "total_node_types": sum(len(c.node_types) for c in connectors),
    }


@router.get("/categories")
async def get_categories():
    """Get connector categories with counts."""
    return {"categories": get_connector_categories()}


@router.get("/{connector_id}")
async def get_connector_detail(connector_id: str):
    """Get detailed info about a specific connector."""
    connector = get_connector(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector not found: {connector_id}")

    return {
        "id": connector.id,
        "name": connector.name,
        "description": connector.description,
        "category": connector.category,
        "icon": connector.icon,
        "color": connector.color,
        "auth_type": connector.auth_type,
        "auth_fields": connector.auth_fields,
        "node_types": connector.node_types,
        "version": connector.version,
        "documentation_url": connector.documentation_url,
    }


class ConnectorExecuteRequest(BaseModel):
    action: str
    params: dict[str, Any] = {}
    credentials: dict[str, str] | None = None


@router.post("/{connector_id}/execute")
async def execute_connector_action(connector_id: str, request: ConnectorExecuteRequest):
    """Execute a connector action."""
    result = await execute_connector(connector_id, request.action, request.params, request.credentials)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Execution failed"))
    return result
