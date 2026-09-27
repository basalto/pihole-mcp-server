"""Main entry point for Pi-hole MCP Server."""

from __future__ import annotations

import importlib.metadata
import os
from typing import Any, Literal, cast

from fastmcp import FastMCP

from .auth import StaticTokenAuth
from .client import PiHoleClient, PiHoleError
from .config import Settings

settings = Settings()

_auth_provider = StaticTokenAuth(settings.mcp_auth_token) if settings.mcp_auth_token else None
mcp = FastMCP("Pi-hole MCP Server", auth=_auth_provider)

if _auth_provider is not None:
    print("MCP bearer-token authentication enabled")
else:
    print("WARNING: MCP auth is DISABLED (MCP_AUTH_TOKEN not set) - server is unauthenticated")


async def _client() -> PiHoleClient:
    """Create and authenticate a Pi-hole client, raising a clean error on failure."""
    client = PiHoleClient(
        settings.pihole_url,
        settings.pihole_api_password,
        timeout=settings.request_timeout,
    )
    try:
        await client.authenticate()
    except Exception as exc:  # noqa: BLE001 - surface as tool error
        await client.aclose()
        raise PiHoleError(
            f"Failed to connect/authenticate to Pi-hole at {settings.pihole_url}: {exc}"
        ) from exc
    return client


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def health_check() -> dict[str, str]:
    """Health check to verify the server is running and can reach Pi-hole.

    Returns:
        Status information plus Pi-hole connectivity.
    """
    try:
        client = await _client()
    except PiHoleError as exc:
        return {
            "status": "unhealthy",
            "error": str(exc),
            "version": importlib.metadata.version("pihole-mcp-server"),
        }
    try:
        await client.summary()
        pihole_reachable = "ok"
    except PiHoleError as exc:
        pihole_reachable = f"error: {exc}"
    finally:
        await client.aclose()
    return {
        "status": "healthy" if pihole_reachable == "ok" else "unhealthy",
        "pihole_reachable": pihole_reachable,
        "pihole_url": settings.pihole_url,
        "version": importlib.metadata.version("pihole-mcp-server"),
    }


@mcp.tool()
async def get_summary() -> dict[str, Any]:
    """Get Pi-hole DNS query summary statistics.

    Returns:
        Total/blocked/forwarded/cached query counts, unique domains, active
        clients, and gravity (blocklist) stats.
    """
    client = await _client()
    try:
        return await client.summary()
    finally:
        await client.aclose()


@mcp.tool()
async def get_query_types() -> dict[str, Any]:
    """Get breakdown of DNS queries by record type (A, AAAA, etc.).

    Returns:
        Query-type distribution with counts and percentages.
    """
    client = await _client()
    try:
        return await client.query_types()
    finally:
        await client.aclose()


@mcp.tool()
async def get_upstreams() -> dict[str, Any]:
    """Get upstream DNS resolver statistics.

    Returns:
        Per-upstream query counts, response times, and failure rates.
    """
    client = await _client()
    try:
        return await client.upstreams()
    finally:
        await client.aclose()


@mcp.tool()
async def get_top_domains(count: int = 10, blocked: bool = False) -> dict[str, Any]:
    """Get the most-queried domains.

    Args:
        count: Number of top domains to return (default 10).
        blocked: True for most-blocked domains, False for most-allowed (default).

    Returns:
        Ranked list of domains with query counts.
    """
    client = await _client()
    try:
        return await client.top_domains(count=count, blocked=blocked)
    finally:
        await client.aclose()


@mcp.tool()
async def get_top_clients(count: int = 10, blocked: bool = False) -> dict[str, Any]:
    """Get the most active clients by DNS query volume.

    Args:
        count: Number of top clients to return (default 10).
        blocked: True for top-blocked clients, False for most-active (default).

    Returns:
        Ranked list of clients (IP, name, count) with totals.
    """
    client = await _client()
    try:
        return await client.top_clients(count=count, blocked=blocked)
    finally:
        await client.aclose()


@mcp.tool()
async def get_queries(
    length: int = 50,
    client_filter: str | None = None,
    domain: str | None = None,
    status: str | None = None,
    type: str | None = None,
    upstream: str | None = None,
    from_timestamp: int | None = None,
    until_timestamp: int | None = None,
) -> dict[str, Any]:
    """Fetch recent DNS queries with optional filters. THE tool for per-device DNS analysis.

    Use client_filter (a client IP, e.g. "192.168.5.39") to see exactly which
    domains a single device queried, when, via which upstream, and whether each
    was allowed (FORWARDED/CACHE) or blocked (GRAVITY/REGEX).

    Args:
        length: Maximum number of queries to return (default 50).
        client_filter: Client IP or name to filter on.
        domain: Exact domain match; supports "*" wildcards (e.g. "*tiktok*").
        status: GRAVITY, REGEX, FORWARDED, CACHE, CACHE_STALE, IN_PROGRESS,
            SPECIAL_DOMAIN, or UNKNOWN. (v6 has no "BLOCKED" — blocked queries
            are GRAVITY or REGEX.)
        type: DNS record type (A, AAAA, CNAME, ...).
        upstream: Upstream resolver IP to filter on.
        from_timestamp: Earliest query time (Unix epoch seconds).
        until_timestamp: Latest query time (Unix epoch seconds).

    Returns:
        Query records with domain, client IP/name, status, type, upstream,
        reply, and timestamps, plus pagination cursor and totals.
    """
    client = await _client()
    try:
        return await client.queries(
            length=length,
            client=client_filter,
            domain=domain,
            status=status,
            type=type,
            upstream=upstream,
            from_=from_timestamp,
            until=until_timestamp,
        )
    finally:
        await client.aclose()


@mcp.tool()
async def get_history(length: int = 100) -> dict[str, Any]:
    """Get time-bucketed DNS query history.

    Args:
        length: Number of history buckets to return (default 100).

    Returns:
        Per-bucket totals: total, cached, blocked, forwarded queries.
    """
    client = await _client()
    try:
        return await client.history(length=length)
    finally:
        await client.aclose()


@mcp.tool()
async def get_groups() -> dict[str, Any]:
    """Get Pi-hole client groups.

    Returns:
        List of client groups with membership.
    """
    client = await _client()
    try:
        return await client.groups()
    finally:
        await client.aclose()


@mcp.tool()
async def get_lists() -> dict[str, Any]:
    """Get Pi-hole adlists/blocklists.

    Returns:
        List of configured block/allow lists with status, entry counts, and
        last-update timestamps.
    """
    client = await _client()
    try:
        return await client.lists()
    finally:
        await client.aclose()


@mcp.tool()
async def get_blocking_status() -> dict[str, Any]:
    """Get current DNS blocking status.

    Returns:
        Whether blocking is enabled and any active timer.
    """
    client = await _client()
    try:
        return await client.blocking_status()
    finally:
        await client.aclose()


@mcp.tool()
async def set_blocking(enabled: bool, timer: int | None = None) -> dict[str, Any]:
    """Enable or disable Pi-hole DNS blocking globally.

    This changes live configuration — call it only when the user explicitly
    asked. Read the current state first with get_blocking_status.

    Args:
        enabled: True to enable blocking, False to disable (pause) it.
        timer: Optional auto re-enable delay in seconds (0 = indefinite).

    Returns:
        New blocking state.
    """
    client = await _client()
    try:
        return await client.set_blocking(enabled=enabled, timer=timer)
    finally:
        await client.aclose()


@mcp.tool()
async def get_info(section: str = "system") -> dict[str, Any]:
    """Get Pi-hole system information.

    Args:
        section: One of system, version, ftl, database, sensors, host.

    Returns:
        System/version/FTL/database/sensor/host details.
    """
    client = await _client()
    try:
        return await client.info(section)
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the MCP server."""
    import uvicorn
    from starlette.middleware.cors import CORSMiddleware

    transport = os.getenv("FASTMCP_TRANSPORT", "stdio")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "3100"))

    print(f"Starting Pi-hole MCP Server (transport={transport}, port={port})")
    print(f"Pi-hole URL: {settings.pihole_url}")

    if transport in ("streamable-http", "http", "sse"):
        http_transport = cast(Literal["http", "streamable-http", "sse"], transport)
        starlette_app = mcp.http_app(transport=http_transport)
        cors_app = CORSMiddleware(
            app=starlette_app,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        uvicorn.run(cors_app, host=host, port=port, lifespan="on")
    else:
        run_transport = cast(Literal["stdio", "http", "sse", "streamable-http"], transport)
        mcp.run(transport=run_transport)


if __name__ == "__main__":
    main()
