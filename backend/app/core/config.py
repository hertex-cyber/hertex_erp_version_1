from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    PROJECT_NAME: str = "Hertex ERP"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = (
        "postgresql+asyncpg://hertex:hertex_dev_password@localhost:5432/hertex_erp"
    )

    JWT_SECRET: str = "change-me-to-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MFA_CHALLENGE_EXPIRE_MINUTES: int = 5
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    REDIS_URL: str = "redis://localhost:6379/0"

    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    WHATSAPP_TOKEN: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    WHATSAPP_VERIFY_TOKEN: str | None = None
    WHATSAPP_API_BASE: str = "https://graph.facebook.com"
    WHATSAPP_API_VERSION: str = "v23.0"
    META_APP_SECRET: str | None = None
    META_ACCESS_TOKEN: str | None = None
    RAZORPAY_KEY_ID: str | None = None
    RAZORPAY_KEY_SECRET: str | None = None

    AUTO_CREATE_TABLES: bool = False
    AUTO_SEED: bool = False
    SEED_DEMO_DATA: bool = True

    SEED_ADMIN_EMAIL: str = "admin@hertex.dev"
    SEED_ADMIN_PASSWORD: str = "Admin@12345"
    SEED_DEMO_TENANT: str = "Hertex Demo Co"

    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_REQUIRE_UPPER: bool = True
    PASSWORD_REQUIRE_LOWER: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SYMBOL: bool = True
    PASSWORD_HISTORY_SIZE: int = 5
    MAX_FAILED_LOGINS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15
    AUTH_RATE_LIMIT_PER_MINUTE: int = 20

    MFA_ISSUER: str = "Hertex ERP"
    REQUIRE_MFA_FOR_ADMINS: bool = False
    REFRESH_COOKIE_NAME: str = "hertex_refresh"
    CSRF_COOKIE_NAME: str = "hertex_csrf"

    # Settings module (half A): secret vault (AES-256-GCM). Generate with:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    SETTINGS_ENCRYPTION_KEY: str = ""
    SETTINGS_ENCRYPTION_KEY_VERSION: int = 1
    SETTINGS_ENCRYPTION_KEY_PREVIOUS: str = ""
    SETTINGS_ENCRYPTION_KEY_VERSION_PREVIOUS: int | None = None
    SETTINGS_ENCRYPTION_KEY_RING: str = ""
    EXPERIMENTAL_SETTINGS_ENCRYPTION_KEY: str = ""
    SETTINGS_CACHE_TTL_SECONDS: int = 300

    @staticmethod
    def _derive_key_bytes(raw: str) -> bytes:
        import hashlib

        value = raw or ""
        if len(value) == 64:
            try:
                return bytes.fromhex(value)
            except ValueError:
                pass
        if value:
            return value.encode("utf-8").ljust(32, b"0")[:32]
        return hashlib.sha256(b"hertex-dev-settings-key").digest()

    @property
    def encryption_key_bytes(self) -> bytes:
        """32 raw bytes for AES-256-GCM; derived from the hex or raw key string."""
        return self._derive_key_bytes(self.SETTINGS_ENCRYPTION_KEY)

    def encryption_keys(self) -> dict[int, bytes]:
        import json

        keys = {self.SETTINGS_ENCRYPTION_KEY_VERSION: self.encryption_key_bytes}
        previous_version = self.SETTINGS_ENCRYPTION_KEY_VERSION_PREVIOUS
        if self.SETTINGS_ENCRYPTION_KEY_PREVIOUS:
            if previous_version is None:
                previous_version = self.SETTINGS_ENCRYPTION_KEY_VERSION - 1
            if previous_version and previous_version != self.SETTINGS_ENCRYPTION_KEY_VERSION:
                keys[previous_version] = self._derive_key_bytes(
                    self.SETTINGS_ENCRYPTION_KEY_PREVIOUS
                )
        ring = (self.SETTINGS_ENCRYPTION_KEY_RING or "").strip()
        if ring:
            raw_ring = json.loads(ring)
            if not isinstance(raw_ring, dict):
                raise ValueError("SETTINGS_ENCRYPTION_KEY_RING must be a JSON object")
            for version, raw in raw_ring.items():
                keys[int(version)] = self._derive_key_bytes(str(raw))
        return keys

    @property
    def cookie_secure(self) -> bool:
        return self.ENVIRONMENT not in {"development", "test"}

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+asyncpg://", 1)
        elif value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def sync_database_url(self) -> str:
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
