"""Unit tests for settings and auth."""

from __future__ import annotations

import pytest

from pihole_mcp.auth import StaticTokenAuth
from pihole_mcp.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.pihole_url == "http://localhost:8080"
    assert s.pihole_api_password == ""
    assert s.mcp_auth_token is None


def test_settings_env_aliases(monkeypatch):
    monkeypatch.setenv("PIHOLE_URL", "http://192.168.1.19:8080")
    monkeypatch.setenv("PIHOLE_API_PASSWORD", "pw")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "tok")
    s = Settings(_env_file=None)
    assert s.pihole_url == "http://192.168.1.19:8080"
    assert s.pihole_api_password == "pw"
    assert s.mcp_auth_token == "tok"


def test_static_token_auth_requires_token():
    with pytest.raises(ValueError):
        StaticTokenAuth("")


async def test_static_token_auth_verify():
    auth = StaticTokenAuth("sekret")
    ok = await auth.verify_token("sekret")
    assert ok is not None
    assert ok.token == "sekret"
    assert ok.client_id == "pihole-mcp-server"


async def test_static_token_auth_rejects_wrong_and_empty():
    auth = StaticTokenAuth("sekret")
    assert await auth.verify_token("wrong") is None
    assert await auth.verify_token("") is None
    assert await auth.verify_token(None) is None
