"""Main entry point for Pi-hole MCP Server."""

from __future__ import annotations

import importlib.metadata
from typing import Any

import httpx
from basalto_mcp import make_auth, serve
from fastmcp import FastMCP

from .client import PiHoleClient, PiHoleError
from .config import Settings

settings = Settings()

_auth_provider = make_auth(settings, client_id="pihole-mcp-server")
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
        client_filter: Client IP to filter on (e.g. "192.168.5.39").
        domain: Exact domain match; supports "*" wildcards (e.g. "*tiktok*").
        status: GRAVITY, REGEX, FORWARDED, CACHE, CACHE_STALE, IN_PROGRESS,
            SPECIAL_DOMAIN, or UNKNOWN. (v6 has no "BLOCKED" — blocked queries
            are GRAVITY or REGEX.)
        type: DNS record type (A, AAAA, CNAME, ...).
        upstream: Upstream resolver as "IP#port" (e.g. "192.168.1.93#53").
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


# ---------------------------------------------------------------------------
# Calling-home / beacon analysis (pihole-beacon-api sidecar over the FTL DB)
# ---------------------------------------------------------------------------
#
# The v6 API's /api/queries only serves the in-memory window (~18h), so
# per-client, per-domain history over weeks is read from the FTL long-term
# SQLite DB by the pihole-beacon-api sidecar (PIHOLE_BEACON_URL) and exposed
# as these two tools. Coverage caveat: only clients that use Pi-hole as DNS #1
# (the IoT VLAN, 192.168.5.0/25) appear here — infra/VMs resolve via BIND
# directly and never show up.


async def _beacon_get(path: str, **params: Any) -> Any:
    """GET from the beacon sidecar, raising a clean error on failure."""
    if not settings.beacon_url:
        raise RuntimeError(
            "beacon analysis is not configured (PIHOLE_BEACON_URL is unset). "
            "The pihole-beacon-api sidecar must be running on the Pi-hole host."
        )
    base = settings.beacon_url.rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as http:
        resp = await http.get(
            f"{base}{path}",
            params={k: v for k, v in params.items() if v is not None},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"beacon-api error {resp.status_code}: {resp.text[:300]}")
    return resp.json()


@mcp.tool()
async def get_dns_beacons(
    days: int = 30,
    min_count: int = 10,
    min_span_days: float = 1.0,
    client_ip: str | None = None,
    domain: str | None = None,
    blocked_only: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Ranked calling-home / periodic-beacon (client, domain) pairs over weeks.

    THE tool for "which IoT device keeps phoning home to domain X, and how
    regularly". Aggregates the Pi-hole FTL long-term query log (up to 91 days)
    per (client, domain) pair and returns, for each: total query count, how
    many were blocked vs allowed, first/last seen, span in days, presence ratio
    (fraction of the span's hours with at least one query — a high ratio with
    steady traffic is a persistent beacon), and median/min/max inter-query gap
    seconds (the cadence). Sorted by count, then span.

    Note: only clients that use Pi-hole as their resolver appear (the IoT VLAN
    at this homelab). Infra/VMs resolve via BIND and are invisible here — use
    the unifi-mcp flow tools for those.

    Args:
        days: Lookback window in days (1-91, default 30).
        min_count: Only pairs with at least this many queries (default 10).
        min_span_days: Only pairs spanning at least this many days (default 1).
        client_ip: Restrict to one client IP (e.g. "192.168.5.55").
        domain: Restrict to a substring match on the domain (e.g. "amazon").
        blocked_only: True to return only pairs with blocked queries.
        limit: Maximum pairs to return (default 50, max 500).

    Returns:
        List of beacon records, each with client_ip, domain, count, blocked,
        allowed, first_seen, last_seen, span_days, presence_ratio,
        median_gap_seconds, min_gap_seconds, max_gap_seconds.
    """
    return await _beacon_get(
        "/beacons",
        days=days,
        min_count=min_count,
        min_span_days=min_span_days,
        client_ip=client_ip,
        domain=domain,
        blocked_only=blocked_only,
        limit=limit,
    )


@mcp.tool()
async def get_dns_callers(
    days: int = 30,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Per-client DNS query rollup over weeks — who queries how much, and how
    consistently.

    Aggregates the Pi-hole FTL long-term query log per client: total queries,
    unique domains, blocked count, block ratio, first/last seen, span in days,
    and presence ratio (fraction of the span's hours the client was active).
    Sorted by query volume. The "who is the noisiest DNS caller" view; combine
    with get_dns_beacons to drill into what a noisy client is phoning.

    Note: only clients that use Pi-hole as their resolver appear (the IoT VLAN
    at this homelab).

    Args:
        days: Lookback window in days (1-91, default 30).
        limit: Maximum clients to return (default 50, max 200).

    Returns:
        List of client records: client_ip, queries, unique_domains, blocked,
        block_ratio, first_seen, last_seen, span_days, presence_ratio.
    """
    return await _beacon_get("/callers", days=days, limit=limit)


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
    print(f"Pi-hole URL: {settings.pihole_url}")
    serve(mcp, default_port=3100)


if __name__ == "__main__":
    main()
