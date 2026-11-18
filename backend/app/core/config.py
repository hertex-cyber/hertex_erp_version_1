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
