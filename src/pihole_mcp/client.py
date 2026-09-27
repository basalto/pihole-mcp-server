"""Async HTTP client for the Pi-hole v6 API.

Pi-hole v6 authenticates by POSTing the web password to ``/api/auth``, which
returns a session ID (SID). Every subsequent request carries the SID in the
``X-FTL-SID`` header. The SID is long-lived but can be invalidated server-side;
the client transparently re-authenticates on a 401.

All methods return parsed JSON (dict/list). HTTP errors raise ``PiHoleError``.
"""

from __future__ import annotations

from typing import Any

import httpx


class PiHoleError(RuntimeError):
    """Raised when the Pi-hole API returns an error or unexpected payload."""


class PiHoleClient:
    """Authenticated async client for the Pi-hole v6 API."""

    def __init__(
        self,
        base_url: str,
        password: str,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.timeout = timeout
        self._sid: str | None = None
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def __aenter__(self) -> PiHoleClient:
        await self.authenticate()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def authenticate(self) -> str:
        """Authenticate against /api/auth and cache the session ID.

        Returns:
            The session ID (SID).
        """
        resp = await self._client.post(
            f"{self.base_url}/api/auth",
            json={"password": self.password},
        )
        if resp.status_code != 200:
            raise PiHoleError(f"Pi-hole auth failed (HTTP {resp.status_code}): {resp.text[:200]}")
        data = resp.json()
        sid = (data.get("session") or {}).get("sid")
        if not sid:
            raise PiHoleError(f"Pi-hole auth returned no session ID: {data}")
        self._sid = sid
        return sid

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        _retry: bool = True,
    ) -> Any:
        """Perform an authenticated request, re-authenticating once on 401."""
        if not self._sid:
            await self.authenticate()
        headers = {"X-FTL-SID": self._sid}
        resp = await self._client.request(
            method,
            f"{self.base_url}{path}",
            params=params,
            json=json,
            headers=headers,
        )
        if resp.status_code == 401 and _retry:
            # SID may have been invalidated — re-auth and retry exactly once.
            await self.authenticate()
            return await self._request(method, path, params=params, json=json, _retry=False)
        if resp.status_code >= 400:
            raise PiHoleError(
                f"Pi-hole {method} {path} failed (HTTP {resp.status_code}): {resp.text[:200]}"
            )
        return resp.json()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any]) -> Any:
        return await self._request("POST", path, json=json)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def summary(self) -> dict[str, Any]:
        return await self.get("/api/stats/summary")

    async def query_types(self) -> dict[str, Any]:
        return await self.get("/api/stats/query_types")

    async def upstreams(self) -> dict[str, Any]:
        return await self.get("/api/stats/upstreams")

    async def top_domains(self, count: int = 10, blocked: bool = False) -> dict[str, Any]:
        path = "/api/stats/top_domains"
        if blocked:
            path = "/api/stats/top_domains/blocked"
        return await self.get(path, params={"count": count})

    async def top_clients(self, count: int = 10, blocked: bool = False) -> dict[str, Any]:
        path = "/api/stats/top_clients"
        if blocked:
            path = "/api/stats/top_clients/blocked"
        return await self.get(path, params={"count": count})

    # ------------------------------------------------------------------
    # Queries / history
    # ------------------------------------------------------------------

    async def queries(
        self,
        length: int = 50,
        *,
        client: str | None = None,
        domain: str | None = None,
        status: str | None = None,
        type: str | None = None,
        upstream: str | None = None,
        from_: int | None = None,
        until: int | None = None,
    ) -> dict[str, Any]:
        """Fetch recent DNS queries.

        Filters (all optional, combined with AND by the server):
            client:   client IP (e.g. "192.168.5.39")
            domain:   exact domain match; supports "*" wildcards (e.g. "*tiktok*")
            status:   GRAVITY, REGEX, FORWARDED, CACHE, CACHE_STALE, IN_PROGRESS,
                      SPECIAL_DOMAIN, UNKNOWN (v6 has no "BLOCKED" status — blocked
                      queries surface as GRAVITY or REGEX)
            type:     DNS record type (A, AAAA, CNAME, ...)
            upstream: upstream resolver as "IP#port" (e.g. "192.168.1.93#53") —
                      the plain IP alone returns nothing
            from_:    earliest timestamp (Unix epoch seconds)
            until:    latest timestamp (Unix epoch seconds)
        """
        params: dict[str, Any] = {"length": length}
        if client:
            params["client_ip"] = client
        if domain:
            params["domain"] = domain
        if status:
            params["status"] = status
        if type:
            params["type"] = type
        if upstream:
            params["upstream"] = upstream
        if from_ is not None:
            params["from"] = from_
        if until is not None:
            params["until"] = until
        return await self.get("/api/queries", params=params)

    async def history(self, length: int = 100) -> dict[str, Any]:
        return await self.get("/api/history", params={"length": length})

    # ------------------------------------------------------------------
    # Configuration / status
    # ------------------------------------------------------------------

    async def groups(self) -> dict[str, Any]:
        return await self.get("/api/groups")

    async def lists(self) -> dict[str, Any]:
        return await self.get("/api/lists")

    async def blocking_status(self) -> dict[str, Any]:
        return await self.get("/api/dns/blocking")

    async def set_blocking(self, enabled: bool, timer: int | None = None) -> dict[str, Any]:
        """Enable or disable DNS blocking globally.

        Args:
            enabled: True to enable blocking, False to disable.
            timer: Optional auto-re-enable delay in seconds (0 = indefinite).
        """
        payload: dict[str, Any] = {"blocking": enabled}
        if timer is not None:
            payload["timer"] = timer
        return await self.post("/api/dns/blocking", json=payload)

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    async def info(self, section: str) -> dict[str, Any]:
        valid = {"system", "version", "ftl", "database", "sensors", "host"}
        if section not in valid:
            raise PiHoleError(f"Unknown info section '{section}' (valid: {sorted(valid)})")
        return await self.get(f"/api/info/{section}")
