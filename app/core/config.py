import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "changethis"
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "https://app.qorebit.ai"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        origins = [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST,
            "http://localhost:3000",
            "https://localhost:3000",
            "http://127.0.0.1:3000",
            "https://127.0.0.1:3000",
            "http://localhost:3001",
            "https://localhost:3001",
            "http://127.0.0.1:3001",
            "https://127.0.0.1:3001",
            "http://localhost:5173",
            "https://localhost:5173",
            "http://127.0.0.1:5173",
            "https://127.0.0.1:5173"
        ]
        return origins

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @model_validator(mode="before")
    @classmethod
    def _strip_whitespace(cls, data: Any) -> Any:
        """Strip whitespace from critical strings"""
        if isinstance(data, dict):
            for key in ["POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"]:
                if key in data and isinstance(data[key], str):
                    data[key] = data[key].strip()
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        # For Render PostgreSQL internal connections: no SSL needed
        # Internal hostnames look like: dpg-xxx-a (no .render.com suffix)
        # External hostnames have .oregon-postgres.render.com and need SSL
        is_render_internal = (
            self.POSTGRES_SERVER.startswith("dpg-") and 
            ".render.com" not in self.POSTGRES_SERVER
        )
        
        if self.ENVIRONMENT == "local":
            query = None
        else:
            # Force SSL for ALL non-local environments to handle public IP routing
            query = "sslmode=require"
        
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
            query=query,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    # Postmark Email Service Configuration
    POSTMARK_SERVER_TOKEN: str | None = None
    POSTMARK_MESSAGE_STREAM: str = "outbound"  # Default stream for transactional emails
    EMAIL_PROVIDER: Literal["smtp", "postmark"] = "smtp"  # smtp or postmark

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        if self.EMAIL_PROVIDER == "postmark":
            return bool(self.POSTMARK_SERVER_TOKEN and self.EMAILS_FROM_EMAIL)
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str
    
    # OpenRouter Configuration
    OPENROUTER_API_KEY: str = ""
    AI_MODEL: str = "openai/gpt-4o"  # Free model on OpenRouter

    # RequestyAI Configuration (for AI Engine endpoints)
    REQUESTY_AI_BASE_URL: str = "https://router.requesty.ai/v1"
    REQUESTY_AI_API_KEY: str = ""
    REQUESTY_AI_TIMEOUT: int = 60  # Timeout in seconds
    REQUESTY_AI_MAX_RETRIES: int = 3  # Maximum number of retries

    # Tavily Search API Configuration (for web search in AI chat)
    TAVILY_API_KEY: str = ""  # Get free API key at https://tavily.com

    # Payment Provider Configuration
    PAYMENT_PROVIDER: str = "paystack"  # Active provider: paystack, monnify

    # Paystack Payment Gateway Configuration (PRIMARY)
    PAYSTACK_SECRET_KEY: str = "" 
    PAYSTACK_PUBLIC_KEY: str = ""
    PAYSTACK_WEBHOOK_SECRET: str = ""  # For verifying webhook signatures (or use Secret Key if signatures use that)
    PAYSTACK_BASE_URL: str = "https://api.paystack.co"

    # Monnify Payment Gateway Configuration
    MONNIFY_BASE_URL: str = "https://sandbox.monnify.com"  # Use https://api.monnify.com for production
    MONNIFY_API_KEY: str = ""
    MONNIFY_SECRET_KEY: str = ""
    MONNIFY_CONTRACT_CODE: str = ""
    MONNIFY_WEBHOOK_SECRET: str = ""  # For verifying webhook signatures

    # Credit Conversion Rate
    NAIRA_TO_CREDIT_RATE: int = 1650  # ₦1650 = 1 AI Credit (USD equivalent)

    # Google OAuth Configuration (for Google Drive integration)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

    # Cloudflare R2 Storage Configuration
    R2_ENDPOINT_URL: str = ""  # https://<account_id>.r2.cloudflarestorage.com
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "qorebit-documents"
    R2_PUBLIC_URL: str = ""  # Public URL for accessing files

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # RequestyAI API URL (for embeddings)
    REQUESTY_API_URL: str = "https://router.requesty.ai/v1"
    REQUESTY_API_KEY: str = ""

    # Postmark API Token (for email tool)
    POSTMARK_API_TOKEN: str = ""

    # Copilot settings removed
    @model_validator(mode="after")
    def _fix_production_defaults(self) -> Self:
        # 1. Handle full URL provided in POSTGRES_SERVER (common mistake)
        if self.POSTGRES_SERVER.startswith("postgresql"):
            try:
                from pydantic import PostgresDsn
                dsn = PostgresDsn(self.POSTGRES_SERVER)
                self.POSTGRES_SERVER = dsn.host or self.POSTGRES_SERVER
                self.POSTGRES_PORT = dsn.port or self.POSTGRES_PORT
                self.POSTGRES_USER = dsn.user or self.POSTGRES_USER
                self.POSTGRES_PASSWORD = dsn.password or self.POSTGRES_PASSWORD
                self.POSTGRES_DB = dsn.path.lstrip("/") if dsn.path else self.POSTGRES_DB
            except Exception:
                pass

        return self

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
