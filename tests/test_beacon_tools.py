"""Unit tests for the beacon-analysis MCP tools (get_dns_beacons, get_dns_callers)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import pihole_mcp.main as main


@pytest.fixture
def mock_http(mocker):
    """Patch httpx.AsyncClient so the tools hit an in-memory client."""
    client_cls = mocker.patch.object(main.httpx, "AsyncClient")
    client = client_cls.return_value.__aenter__.return_value
    client.get = AsyncMock()
    return client


def _resp(payload):
    r = type("Resp", (), {})()
    r.status_code = 200
    r.text = ""
    r._payload = payload

    def json():
        return r._payload

    r.json = json
    return r


async def test_get_dns_beacons_calls_sidecar(mocker, mock_http):
    mocker.patch.object(main.settings, "beacon_url", "http://localhost:8788")
    mock_http.get.return_value = _resp([{"domain": "mads.amazon-adsystem.com", "count": 2822}])

    result = await main.get_dns_beacons(days=30, min_count=50, blocked_only=True, limit=5)

    args, kwargs = mock_http.get.await_args
    assert args[0] == "http://localhost:8788/beacons"
    assert kwargs["params"] == {
        "days": 30,
        "min_count": 50,
        "min_span_days": 1.0,
        "blocked_only": True,
        "limit": 5,
    }
    assert result[0]["domain"] == "mads.amazon-adsystem.com"


async def test_get_dns_callers_calls_sidecar(mocker, mock_http):
    mocker.patch.object(main.settings, "beacon_url", "http://localhost:8788")
    mock_http.get.return_value = _resp([{"client_ip": "192.168.5.55", "queries": 53411}])

    result = await main.get_dns_callers(days=7, limit=3)

    args, kwargs = mock_http.get.await_args
    assert args[0] == "http://localhost:8788/callers"
    assert kwargs["params"] == {"days": 7, "limit": 3}
    assert result[0]["client_ip"] == "192.168.5.55"


async def test_beacon_get_raises_without_url(mocker):
    mocker.patch.object(main.settings, "beacon_url", "")
    with pytest.raises(RuntimeError, match="PIHOLE_BEACON_URL is unset"):
        await main.get_dns_callers()


async def test_beacon_get_raises_on_http_error(mocker, mock_http):
    mocker.patch.object(main.settings, "beacon_url", "http://localhost:8788")
    r = type("Resp", (), {})()
    r.status_code = 500
    r.text = "boom"
    mock_http.get.return_value = r

    with pytest.raises(RuntimeError, match="beacon-api error 500"):
        await main.get_dns_callers()
