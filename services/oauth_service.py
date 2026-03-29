"""
OAuth Service for Google/GitHub/Microsoft Authentication

Provides OAuth 2.0 integration with automatic token refresh logic.
"""

import logging
import os
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import InvalidToken
from fastapi import HTTPException

try:
    from apps.backend.core.resilience import retry_with_backoff
except ImportError:

    def retry_with_backoff(**_kw):
        def _noop(fn):
            return fn

        return _noop

logger = logging.getLogger(__name__)


class OAuthProvider(str, Enum):
    """Supported OAuth providers."""

    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"
    DISCORD = "discord"


class OAuthService:
    """
    OAuth authentication service with token refresh logic.

    Supports Google, GitHub, and Microsoft OAuth 2.0 flows.
    """

    # Allowed redirect URI hosts — prevents open-redirect attacks.
    # Populated from OAUTH_ALLOWED_REDIRECT_HOSTS env var (comma-separated).
    _allowed_redirect_hosts: set = set()

    def __init__(self) -> None:
        self.providers = {}
        self._initialize_providers()

        # Build allowed redirect hosts from environment
        raw = os.getenv("OAUTH_ALLOWED_REDIRECT_HOSTS", "")
        if raw:
            self._allowed_redirect_hosts = {h.strip().lower() for h in raw.split(",") if h.strip()}

        # Always allow the configured frontend/API host
        api_base = os.getenv("API_BASE", "")
        frontend_url = os.getenv("NEXT_PUBLIC_APP_URL", "") or os.getenv("FRONTEND_URL", "")
        for url in (api_base, frontend_url):
            if url:
                parsed = urlparse(url)
                if parsed.hostname:
                    self._allowed_redirect_hosts.add(parsed.hostname.lower())

        # Fallback: allow localhost for development
        if os.getenv("HELIX_ENV", "production") == "development":
            self._allowed_redirect_hosts.update({"localhost", "127.0.0.1"})

    def _validate_redirect_uri(self, redirect_uri: str) -> None:
        """Validate that redirect_uri points to an allowed host."""
        parsed = urlparse(redirect_uri)
        if parsed.scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="Invalid redirect URI scheme")
        host = (parsed.hostname or "").lower()
        if not host:
            raise HTTPException(status_code=400, detail="Invalid redirect URI")
        if self._allowed_redirect_hosts and host not in self._allowed_redirect_hosts:
            logger.warning("Rejected OAuth redirect_uri to disallowed host: %s", host)
            raise HTTPException(status_code=400, detail="Redirect URI host not allowed")

    def _initialize_providers(self) -> None:
        """Initialize OAuth providers with configuration."""
        # Google OAuth (check both naming conventions for compatibility)
        google_client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "") or os.getenv("GOOGLE_CLIENT_ID", "")
        google_client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "") or os.getenv("GOOGLE_CLIENT_SECRET", "")

        if google_client_id and google_client_secret:
            self.providers[OAuthProvider.GOOGLE] = {
                "client_id": google_client_id,
                "client_secret": google_client_secret,
                "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
                "scopes": [
                    "openid",
                    "email",
                    "profile",
                ],
            }
            logger.info("✅ Google OAuth configured")
        else:
            logger.warning("⚠️  Google OAuth not configured (missing credentials)")

        # GitHub OAuth (check both naming conventions for compatibility)
        github_client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID", "") or os.getenv("GITHUB_CLIENT_ID", "")
        github_client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "") or os.getenv("GITHUB_CLIENT_SECRET", "")

        if github_client_id and github_client_secret:
            self.providers[OAuthProvider.GITHUB] = {
                "client_id": github_client_id,
                "client_secret": github_client_secret,
                "authorize_url": "https://github.com/login/oauth/authorize",
                "token_url": "https://github.com/login/oauth/access_token",
                "userinfo_url": "https://api.github.com/user",
                "scopes": [
                    "read:user",
                    "user:email",
                ],
            }
            logger.info("✅ GitHub OAuth configured")
        else:
            logger.warning("⚠️  GitHub OAuth not configured (missing credentials)")

        # Microsoft OAuth (Azure AD / Entra ID)
        microsoft_client_id = os.getenv("MICROSOFT_OAUTH_CLIENT_ID", "")
        microsoft_client_secret = os.getenv("MICROSOFT_OAUTH_CLIENT_SECRET", "")
        microsoft_tenant = os.getenv("MICROSOFT_OAUTH_TENANT_ID", "common")

        if microsoft_client_id and microsoft_client_secret:
            self.providers[OAuthProvider.MICROSOFT] = {
                "client_id": microsoft_client_id,
                "client_secret": microsoft_client_secret,
                "authorize_url": (f"https://login.microsoftonline.com/{microsoft_tenant}/oauth2/v2.0/authorize"),
                "token_url": (f"https://login.microsoftonline.com/{microsoft_tenant}/oauth2/v2.0/token"),
                "userinfo_url": "https://graph.microsoft.com/v1.0/me",
                "scopes": [
                    "openid",
                    "email",
                    "profile",
                    "User.Read",
                ],
            }
            logger.info("✅ Microsoft OAuth configured")
        else:
            logger.warning("⚠️  Microsoft OAuth not configured (missing credentials)")

        # Discord OAuth
        discord_client_id = os.getenv("DISCORD_CLIENT_ID", "")
        discord_client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")

        if discord_client_id and discord_client_secret:
            self.providers[OAuthProvider.DISCORD] = {
                "client_id": discord_client_id,
                "client_secret": discord_client_secret,
                "authorize_url": "https://discord.com/oauth2/authorize",
                "token_url": "https://discord.com/api/oauth2/token",
                "userinfo_url": "https://discord.com/api/users/@me",
                "scopes": [
                    "identify",
                    "email",
                ],
            }
            logger.info("✅ Discord OAuth configured")
        else:
            logger.warning("⚠️  Discord OAuth not configured (missing credentials)")

    def get_authorization_url(
        self,
        provider: OAuthProvider,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            provider: OAuth provider (google or github)
            redirect_uri: Callback URL after authorization
            state: CSRF protection state token
            code_challenge: PKCE code challenge (RFC 7636)
            code_challenge_method: PKCE challenge method (e.g. "S256")

        Returns:
            Authorization URL to redirect user to
        """
        config = self.providers.get(provider)
        if not config:
            raise HTTPException(
                status_code=400,
                detail=f"OAuth provider {provider} not configured",
            )

        # Validate redirect_uri against allowlist
        self._validate_redirect_uri(redirect_uri)

        params = {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(config["scopes"]),
            "state": state,
        }

        # Provider-specific parameters
        if provider == OAuthProvider.GOOGLE:
            params["access_type"] = "offline"
            params["prompt"] = "consent"  # Force consent to get refresh token
        elif provider == OAuthProvider.MICROSOFT:
            params["response_mode"] = "query"
            params["prompt"] = "consent"  # Force consent to get refresh token

        # PKCE parameters (RFC 7636)
        if code_challenge:
            params["code_challenge"] = code_challenge
        if code_challenge_method:
            params["code_challenge_method"] = code_challenge_method

        # Build URL with proper percent-encoding
        query_string = urlencode(params)
        return f"{config['authorize_url']}?{query_string}"

    @retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
    async def exchange_code(
        self,
        provider: OAuthProvider,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        """
        Exchange authorization code for tokens.

        Args:
            provider: OAuth provider
            code: Authorization code from callback
            redirect_uri: Must match the one used in authorization URL
            code_verifier: PKCE code verifier (RFC 7636)

        Returns:
            Token response with access_token, refresh_token, expires_at
        """
        config = self.providers.get(provider)
        if not config:
            raise HTTPException(
                status_code=400,
                detail=f"OAuth provider {provider} not configured",
            )

        # Validate redirect_uri against allowlist
        self._validate_redirect_uri(redirect_uri)

        # Exchange code for tokens
        exchange_data = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        # Include PKCE verifier if provided (RFC 7636)
        if code_verifier:
            exchange_data["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                config["token_url"],
                data=exchange_data,
                headers={
                    "Accept": "application/json",
                },
            )

            if response.status_code != 200:
                logger.error("OAuth token exchange failed: %s", response.text)
                raise HTTPException(
                    status_code=400,
                    detail="Failed to exchange authorization code",
                )

            token_data = response.json()

        # Calculate expiry time
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now(UTC).timestamp() + expires_in

        return {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_at": expires_at,
            "provider": provider.value,
        }

    @retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
    async def refresh_token(
        self,
        provider: OAuthProvider,
        refresh_token: str,
    ) -> dict[str, Any]:
        """
        Refresh access token using refresh token.

        Args:
            provider: OAuth provider
            refresh_token: Refresh token from previous auth

        Returns:
            New token response
        """
        config = self.providers.get(provider)
        if not config:
            raise HTTPException(
                status_code=400,
                detail=f"OAuth provider {provider} not configured",
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                config["token_url"],
                data={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={
                    "Accept": "application/json",
                },
            )

            if response.status_code != 200:
                logger.error("OAuth token refresh failed: %s", response.text)
                raise HTTPException(
                    status_code=400,
                    detail="Failed to refresh access token",
                )

            token_data = response.json()

        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now(UTC).timestamp() + expires_in

        return {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token", refresh_token),  # GitHub may not return new refresh token
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_at": expires_at,
            "provider": provider.value,
        }

    @retry_with_backoff(max_retries=2, base_delay=1.0, exceptions=(Exception,))
    async def get_user_info(
        self,
        provider: OAuthProvider,
        access_token: str,
    ) -> dict[str, Any]:
        """
        Fetch user information from OAuth provider.

        Args:
            provider: OAuth provider
            access_token: Valid access token

        Returns:
            User information from provider
        """
        config = self.providers.get(provider)
        if not config:
            raise HTTPException(
                status_code=400,
                detail=f"OAuth provider {provider} not configured",
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {access_token}"}

            # GitHub requires Accept header for email visibility
            if provider == OAuthProvider.GITHUB:
                headers["Accept"] = "application/vnd.github+json"

            response = await client.get(
                config["userinfo_url"],
                headers=headers,
            )

            if response.status_code != 200:
                logger.error("Failed to fetch user info: %s", response.text)
                raise HTTPException(
                    status_code=400,
                    detail="Failed to fetch user information",
                )

            user_data = response.json()

        # Normalize user data across providers
        return self._normalize_user_data(provider, user_data)

    def _normalize_user_data(
        self,
        provider: OAuthProvider,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize user data from different OAuth providers."""
        if provider == OAuthProvider.GOOGLE:
            return {
                "provider_id": data.get("id"),
                "email": data.get("email"),
                "email_verified": data.get("verified_email"),
                "name": data.get("name"),
                "picture": data.get("picture"),
                "locale": data.get("locale"),
            }
        elif provider == OAuthProvider.GITHUB:
            # GitHub may not include email in main response
            email = data.get("email")
            if not email and "email" in data:
                email = data.get("email")

            return {
                "provider_id": str(data.get("id")),
                "email": email,
                "email_verified": bool(email),  # Cannot confirm verification via GitHub API
                "name": data.get("name") or data.get("login"),
                "picture": data.get("avatar_url"),
                "login": data.get("login"),
            }
        elif provider == OAuthProvider.MICROSOFT:
            return {
                "provider_id": data.get("id"),
                "email": data.get("mail") or data.get("userPrincipalName"),
                "email_verified": bool(data.get("mail") or data.get("userPrincipalName")),
                "name": data.get("displayName"),
                "picture": None,  # Microsoft requires separate Graph API call for photo
                "given_name": data.get("givenName"),
                "family_name": data.get("surname"),
            }
        elif provider == OAuthProvider.DISCORD:
            # Discord user data structure
            # Avatar URL: https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png
            avatar_hash = data.get("avatar")
            user_id = data.get("id")
            picture = None
            if avatar_hash and user_id:
                picture = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"

            return {
                "provider_id": user_id,
                "email": data.get("email"),
                "email_verified": data.get("verified", False),
                "name": data.get("global_name") or data.get("username"),
                "picture": picture,
                "username": data.get("username"),
                "discriminator": data.get("discriminator"),
            }

        return data


# Global OAuth service instance
oauth_service = OAuthService()


class OAuthTokenStore:
    """
    Store and retrieve OAuth tokens securely.

    Tokens are stored encrypted in the database.
    """

    def __init__(self) -> None:
        from sqlalchemy import select, update

        from apps.backend.db_models import User, get_async_session

        self.get_async_session = get_async_session
        self.select = select
        self.update = update
        self.User = User

    async def store_tokens(
        self,
        user_id: str,
        provider: OAuthProvider,
        tokens: dict[str, Any],
    ) -> bool:
        """
        Store OAuth tokens for a user.

        Encrypts refresh token before storage.
        """
        import base64
        import hashlib

        from cryptography.fernet import Fernet

        # Get encryption key
        encryption_key = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").encode()
        if not encryption_key:
            logger.warning("⚠️ OAUTH_TOKEN_ENCRYPTION_KEY not set")
            return False

        # Create Fernet key from encryption key (must be 32 bytes, base64 encoded)
        key_bytes = hashlib.sha256(encryption_key).digest()
        fernet_key = Fernet(base64.urlsafe_b64encode(key_bytes))
        encrypted_refresh = fernet_key.encrypt(tokens.get("refresh_token", "").encode()).decode()

        async with self.get_async_session()() as session:
            # Store tokens based on provider
            if provider == OAuthProvider.GOOGLE:
                await session.execute(
                    self.update(self.User)
                    .where(self.User.id == user_id)
                    .values(
                        google_access_token=tokens.get("access_token"),
                        google_refresh_token=encrypted_refresh,
                        google_token_expires_at=datetime.fromtimestamp(tokens.get("expires_at"), tz=UTC),
                        auth_provider=OAuthProvider.GOOGLE.value,
                    )
                )
            elif provider == OAuthProvider.GITHUB:
                await session.execute(
                    self.update(self.User)
                    .where(self.User.id == user_id)
                    .values(
                        github_access_token=tokens.get("access_token"),
                        github_refresh_token=encrypted_refresh,
                        github_token_expires_at=datetime.fromtimestamp(tokens.get("expires_at"), tz=UTC),
                        auth_provider=OAuthProvider.GITHUB.value,
                    )
                )
            elif provider == OAuthProvider.MICROSOFT:
                await session.execute(
                    self.update(self.User)
                    .where(self.User.id == user_id)
                    .values(
                        microsoft_access_token=tokens.get("access_token"),
                        microsoft_refresh_token=encrypted_refresh,
                        microsoft_token_expires_at=datetime.fromtimestamp(tokens.get("expires_at"), tz=UTC),
                        auth_provider=OAuthProvider.MICROSOFT.value,
                    )
                )

            await session.commit()

        logger.info("✅ OAuth tokens stored for user %s (%s)", user_id, provider.value)
        return True

    async def get_valid_token(
        self,
        user_id: str,
        provider: OAuthProvider,
    ) -> dict[str, Any] | None:
        """
        Get valid access token, refreshing if necessary.

        Returns valid token dict or None if not found/invalid.
        """
        async with self.get_async_session()() as session:
            result = await session.execute(self.select(self.User).where(self.User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                return None

            # Get token data based on provider
            if provider == OAuthProvider.GOOGLE:
                access_token = user.google_access_token
                refresh_token = user.google_refresh_token
                expires_at = user.google_token_expires_at
            elif provider == OAuthProvider.GITHUB:
                access_token = user.github_access_token
                refresh_token = user.github_refresh_token
                expires_at = user.github_token_expires_at
            elif provider == OAuthProvider.MICROSOFT:
                access_token = getattr(user, "microsoft_access_token", None)
                refresh_token = getattr(user, "microsoft_refresh_token", None)
                expires_at = getattr(user, "microsoft_token_expires_at", None)
            else:
                return None

            if not access_token:
                return None

            # Check if token is expired
            if expires_at and expires_at <= datetime.now(UTC):
                # Need to refresh
                if not refresh_token:
                    logger.warning("No refresh token for user %s", user_id)
                    return None

                # Decrypt refresh token
                import base64
                import hashlib

                from cryptography.fernet import Fernet

                encryption_key = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").encode()
                if encryption_key:
                    key_bytes = hashlib.sha256(encryption_key).digest()
                    fernet_key = Fernet(base64.urlsafe_b64encode(key_bytes))
                    try:
                        decrypted_token = fernet_key.decrypt(refresh_token.encode()).decode()
                    except (ValueError, TypeError) as e:
                        logger.debug("OAuth token decryption invalid data: %s", e)
                        return None
                    except InvalidToken as e:
                        logger.debug("OAuth token decryption invalid token: %s", e)
                        return None
                    except Exception as e:
                        logger.warning(
                            "OAuth token decryption failed for user %s provider %s: %s", user_id, provider, e
                        )
                        return None

                    # Refresh the token
                    new_tokens = await oauth_service.refresh_token(provider, decrypted_token)

                    # Store new tokens
                    await self.store_tokens(user_id, provider, new_tokens)

                    return new_tokens

            return {
                "access_token": access_token,
                "provider": provider.value,
            }


# Global token store
oauth_token_store = OAuthTokenStore()
