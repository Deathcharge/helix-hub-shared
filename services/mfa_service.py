"""
MFA Service with secure secret storage

Provides TOTP generation, verification, and backup codes with Fernet encryption
for MFA secrets and PBKDF2 hashing for backup codes.
"""

import base64
import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime

import pyotp
from cryptography.fernet import Fernet
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# Encryption key for MFA secrets (should be set in environment)
MFA_ENCRYPTION_KEY = os.getenv("MFA_ENCRYPTION_KEY", "")

# Password hashing context for backup codes
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Backup code settings
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8


class MFAService:
    """MFA service with encrypted secret storage and secure backup codes."""

    def __init__(self, encryption_key: str = MFA_ENCRYPTION_KEY) -> None:
        self.encryption_key = encryption_key
        self._fernet: Fernet | None = None
        self._init_fernet()

    def _init_fernet(self) -> None:
        """Initialize Fernet encryption with the provided key."""
        if self.encryption_key:
            try:
                key_bytes = hashlib.sha256(self.encryption_key.encode()).digest()
                fernet_key = base64.urlsafe_b64encode(key_bytes)
                self._fernet = Fernet(fernet_key)
                logger.info("✅ MFA Fernet encryption initialized")
            except Exception as e:
                logger.error("❌ Failed to initialize Fernet: %s", e)
                self._fernet = None
        else:
            # Check if we're in production — refuse to operate without key
            _is_prod = (
                os.getenv("RAILWAY_ENVIRONMENT") == "production" or os.getenv("ENVIRONMENT", "").lower() == "production"
            )
            if _is_prod:
                logger.error("MFA_ENCRYPTION_KEY not set in production — MFA operations will fail")
            else:
                logger.warning("⚠️  MFA_ENCRYPTION_KEY not set - using temporary key (dev only)")
            self._fernet = None

    def generate_secret(self) -> str:
        """Generate a new TOTP secret."""
        return pyotp.random_base32()

    def get_totp_uri(self, secret: str, email: str, issuer: str = "Helix") -> str:
        """Generate TOTP URI for QR code."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)

    def verify_code(self, secret: str, code: str) -> bool:
        """Verify a TOTP code against a secret."""
        try:
            totp = pyotp.TOTP(secret)
            # Allow for time drift (1 interval = 30 seconds)
            return totp.verify(code, valid_window=1)
        except Exception as e:
            logger.error("TOTP verification error: %s", e)
            return False

    def generate_code(self, secret: str) -> str:
        """Generate a TOTP code for a secret (for testing)."""
        totp = pyotp.TOTP(secret)
        return totp.now()

    def generate_backup_codes(self) -> list[str]:
        """Generate secure backup codes."""
        codes = []
        for _ in range(BACKUP_CODE_COUNT):
            code = secrets.token_hex(BACKUP_CODE_LENGTH // 2).upper()
            codes.append(code)
        return codes

    def hash_backup_code(self, code: str) -> str:
        """Hash a backup code using PBKDF2."""
        return pwd_context.hash(code)

    def verify_backup_code(self, code: str, hashed_code: str) -> bool:
        """Verify a backup code against its hash."""
        return pwd_context.verify(code, hashed_code)

    def encrypt_secret(self, secret: str) -> bytes:
        """
        Encrypt MFA secret using Fernet (AES 128).

        Args:
            secret: Plain text MFA secret

        Returns:
            Encrypted bytes

        Raises:
            ValueError: If encryption key not available
        """
        # Check for encryption key at runtime in case it was set after initialization
        if not self._fernet:
            self._init_fernet()

        if not self._fernet:
            raise ValueError("MFA encryption not configured - set MFA_ENCRYPTION_KEY")

        return self._fernet.encrypt(secret.encode())

    def decrypt_secret(self, encrypted_secret: bytes) -> str:
        """
        Decrypt MFA secret.

        Args:
            encrypted_secret: Encrypted bytes from encrypt_secret

        Returns:
            Plain text MFA secret

        Raises:
            ValueError: If decryption fails
        """
        # Check for encryption key at runtime in case it was set after initialization
        if not self._fernet:
            self._init_fernet()

        if not self._fernet:
            raise ValueError("MFA encryption not configured - set MFA_ENCRYPTION_KEY")

        decrypted = self._fernet.decrypt(encrypted_secret)
        return decrypted.decode()


# Global MFA service instance
mfa_service = MFAService()


class MFADatabaseService:
    """Database operations for MFA with encryption."""

    def __init__(self) -> None:
        from sqlalchemy import select, update

        from apps.backend.db_models import User, get_async_session

        self.get_async_session = get_async_session
        self.select = select
        self.update = update
        self.User = User

    async def setup_mfa(
        self,
        user_id: str,
        email: str,
    ) -> tuple[str, str, list[str]]:
        """
        Set up MFA for a user and store encrypted secret in database.

        Returns:
            Tuple of (secret, qr_uri, backup_codes)
        """
        # Generate secret and codes
        secret = mfa_service.generate_secret()
        qr_uri = mfa_service.get_totp_uri(secret, email)
        backup_codes = mfa_service.generate_backup_codes()

        # Encrypt secret for storage
        encrypted_secret = mfa_service.encrypt_secret(secret)

        # Hash backup codes for storage
        hashed_codes = [mfa_service.hash_backup_code(code) for code in backup_codes]

        # Store in database
        async with self.get_async_session()() as session:
            await session.execute(
                self.update(self.User)
                .where(self.User.id == user_id)
                .values(
                    mfa_secret=encrypted_secret,
                    mfa_backup_codes=hashed_codes,
                    mfa_enabled=True,
                    mfa_created_at=datetime.now(UTC),
                )
            )
            await session.commit()

        logger.info("✅ MFA setup completed for user: %s", user_id)
        return secret, qr_uri, backup_codes

    async def verify_mfa(self, user_id: str, code: str) -> bool:
        """Verify MFA code for a user."""
        from apps.backend.db_models import User

        async with self.get_async_session()() as session:
            result = await session.execute(self.select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user or not user.mfa_secret:
                return False

            # Decrypt secret
            try:
                secret = mfa_service.decrypt_secret(user.mfa_secret)
            except Exception as e:
                logger.error("Failed to decrypt MFA secret: %s", e)
                return False

            # Verify TOTP code
            return mfa_service.verify_code(secret, code)

    async def verify_backup_code(self, user_id: str, code: str) -> bool:
        """Verify backup code for a user."""

        async with self.get_async_session()() as session:
            result = await session.execute(self.select(self.User).where(self.User.id == user_id))
            user = result.scalar_one_or_none()

            if not user or not user.mfa_backup_codes:
                return False

            # Check against all stored backup codes
            for hashed_code in user.mfa_backup_codes:
                if mfa_service.verify_backup_code(code, hashed_code):
                    # Remove used code
                    updated_codes = [c for c in user.mfa_backup_codes if c != hashed_code]
                    await session.execute(
                        self.update(self.User).where(self.User.id == user_id).values(mfa_backup_codes=updated_codes)
                    )
                    await session.commit()
                    return True

        return False

    async def disable_mfa(self, user_id: str) -> bool:
        """Disable MFA for a user."""

        async with self.get_async_session()() as session:
            await session.execute(
                self.update(self.User)
                .where(self.User.id == user_id)
                .values(
                    mfa_secret=None,
                    mfa_backup_codes=None,
                    mfa_enabled=False,
                    mfa_created_at=None,
                )
            )
            await session.commit()

        logger.info("✅ MFA disabled for user: %s", user_id)
        return True

    async def is_mfa_enabled(self, user_id: str) -> bool:
        """Check if MFA is enabled for a user."""

        async with self.get_async_session()() as session:
            result = await session.execute(self.select(self.User.mfa_enabled).where(self.User.id == user_id))
            return result.scalar_one_or_none() or False

    async def get_mfa_status(self, user_id: str) -> dict:
        """Get MFA status for a user."""

        async with self.get_async_session()() as session:
            result = await session.execute(self.select(self.User).where(self.User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                return {"enabled": False}

            return {
                "enabled": user.mfa_enabled or False,
                "backup_codes_remaining": (len(user.mfa_backup_codes) if user.mfa_backup_codes else 0),
                "created_at": (user.mfa_created_at.isoformat() if user.mfa_created_at else None),
            }


# Global database MFA service
mfa_db_service = MFADatabaseService()
