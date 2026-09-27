"""Configuration management for Pi-hole MCP Server using Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pihole_url: str = Field(
        default="http://localhost:8080",
        description="Pi-hole web server base URL (scheme://host:port, no trailing slash)",
        validation_alias="PIHOLE_URL",
    )

    pihole_api_password: str = Field(
        default="",
        description="Pi-hole v6 API password (FTLCONF_webserver_api_password)",
        validation_alias="PIHOLE_API_PASSWORD",
    )

    mcp_auth_token: str | None = Field(
        default=None,
        description="Optional bearer token required on HTTP transports",
        validation_alias="MCP_AUTH_TOKEN",
    )

    request_timeout: float = Field(
        default=15.0,
        description="HTTP request timeout in seconds",
        validation_alias="PIHOLE_REQUEST_TIMEOUT",
    )

    log_level: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR)",
        validation_alias="PIHOLE_LOG_LEVEL",
    )
