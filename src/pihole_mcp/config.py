"""Configuration management for Pi-hole MCP Server using Pydantic Settings."""

from basalto_mcp import MCPBaseSettings
from pydantic import Field


class Settings(MCPBaseSettings):
    """Application settings loaded from environment variables and .env file.

    Inherits ``.env`` loading, case-insensitivity, and the optional
    ``mcp_auth_token`` (``MCP_AUTH_TOKEN``) from :class:`MCPBaseSettings`.
    """

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
