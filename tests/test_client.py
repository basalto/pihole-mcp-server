"""Unit tests for the Pi-hole API client."""

from __future__ import annotations

import pytest

from pihole_mcp.client import PiHoleClient, PiHoleError


def _resp(status_code: int, payload: dict | None = None, text: str = ""):
    """Plain (sync) httpx-style response: .json() and .status_code are not awaited."""
    r = type("Resp", (), {})()
    r.status_code = status_code
    r._payload = payload
    r.text = text

    def json():
        return r._payload

    r.json = json
    return r


@pytest.fixture
async def client():
    c = PiHoleClient("http://localhost:8080", "secret", timeout=5.0)
    yield c
    await c.aclose()


async def test_authenticate_stores_sid(client, mocker):
    mocker.patch.object(
        client._client,
        "post",
        new=mocker.AsyncMock(return_value=_resp(200, {"session": {"sid": "abc123"}})),
    )

    sid = await client.authenticate()

    assert sid == "abc123"
    assert client._sid == "abc123"
    client._client.post.assert_awaited_once_with(
        "http://localhost:8080/api/auth", json={"password": "secret"}
    )


async def test_authenticate_rejects_missing_sid(client, mocker):
    mocker.patch.object(
        client._client,
        "post",
        new=mocker.AsyncMock(return_value=_resp(200, {"error": "bad"})),
    )

    with pytest.raises(PiHoleError, match="no session ID"):
        await client.authenticate()


async def test_request_sends_sid_header(client, mocker):
    client._sid = "abc123"
    mocker.patch.object(
        client._client,
        "request",
        new=mocker.AsyncMock(return_value=_resp(200, {"ok": True})),
    )

    result = await client.get("/api/stats/summary")

    assert result == {"ok": True}
    client._client.request.assert_awaited_once_with(
        "GET",
        "http://localhost:8080/api/stats/summary",
        params=None,
        json=None,
        headers={"X-FTL-SID": "abc123"},
    )


async def test_request_reauths_on_401(client, mocker):
    client._sid = "stale"
    mocker.patch.object(
        client._client,
        "request",
        new=mocker.AsyncMock(side_effect=[_resp(401), _resp(200, {"ok": True})]),
    )
    mocker.patch.object(
        client._client,
        "post",
        new=mocker.AsyncMock(return_value=_resp(200, {"session": {"sid": "fresh"}})),
    )

    result = await client.get("/api/stats/summary")

    assert result == {"ok": True}
    assert client._sid == "fresh"
    assert client._client.request.await_count == 2


async def test_request_raises_on_http_error(client, mocker):
    client._sid = "abc123"
    mocker.patch.object(
        client._client,
        "request",
        new=mocker.AsyncMock(return_value=_resp(500, text="boom")),
    )

    with pytest.raises(PiHoleError, match="500"):
        await client.get("/api/stats/summary")


async def test_queries_builds_filter_params(client, mocker):
    client._sid = "abc123"
    mocker.patch.object(
        client._client,
        "request",
        new=mocker.AsyncMock(return_value=_resp(200, {"queries": []})),
    )

    await client.queries(
        length=10,
        client="192.168.5.39",
        domain="*tiktok*",
        status="GRAVITY",
        type="A",
        upstream="192.168.1.93",
        from_=1790520000,
        until=1790527400,
    )

    _, kwargs = client._client.request.await_args
    assert kwargs["params"] == {
        "length": 10,
        "client_ip": "192.168.5.39",
        "domain": "*tiktok*",
        "status": "GRAVITY",
        "type": "A",
        "upstream": "192.168.1.93",
        "from": 1790520000,
        "until": 1790527400,
    }


async def test_info_rejects_unknown_section(client, mocker):
    client._sid = "abc123"
    with pytest.raises(PiHoleError, match="Unknown info section"):
        await client.info("bogus")
