# Pi-hole MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server exposing the
[Pi-hole v6 API](https://ftl.pi-hole.net) as tools for LLM agents. Read DNS query
history, per-client and per-domain breakdowns, blocking status, and manage blocking —
all through a typed, authenticated MCP interface.

Built with [FastMCP](https://gofastmcp.com), Python 3.10+.

## Why

Pi-hole v6's web UI is rich but not scriptable by an agent. This server wraps the
v6 JSON API (`/api/...` with `X-FTL-SID` session auth) so an LLM can answer questions
like *"which domains did 192.168.5.39 query in the last hour?"* or *"is blocking on?"*
without scraping the dashboard.

## Tools

| Tool | Purpose |
|---|---|
| `health_check` | Server + Pi-hole connectivity |
| `get_summary` | Totals: blocked / forwarded / cached / unique domains / clients |
| `get_query_types` | Query breakdown by record type |
| `get_upstreams` | Per-upstream stats |
| `get_top_domains` | Most-queried (or most-blocked) domains |
| `get_top_clients` | Most-active (or top-blocked) clients |
| `get_queries` | Recent DNS queries, filterable by client/domain/status/type/upstream/time |
| `get_history` | Time-bucketed query history |
| `get_groups` | Client groups |
| `get_lists` | Adlists / blocklists with status |
| `get_blocking_status` | Whether blocking is enabled |
| `set_blocking` | Enable / disable blocking (live change) |
| `get_info` | System / version / FTL / database / sensors / host |

## Configuration

Environment variables (or a `.env` file):

| Variable | Required | Default | Description |
|---|---|---|---|
| `PIHOLE_URL` | yes | `http://localhost:8080` | Pi-hole web base URL |
| `PIHOLE_API_PASSWORD` | yes | — | v6 API password (`FTLCONF_webserver_api_password`) |
| `MCP_AUTH_TOKEN` | no | — | Bearer token for the MCP server's HTTP transports |
| `FASTMCP_TRANSPORT` | no | `stdio` | `stdio`, `http`, `streamable-http`, `sse` |
| `FASTMCP_HOST` | no | `0.0.0.0` | Bind address |
| `FASTMCP_PORT` | no | `3100` | Bind port |
| `PIHOLE_REQUEST_TIMEOUT` | no | `15` | HTTP timeout (seconds) |
| `PIHOLE_LOG_LEVEL` | no | `INFO` | Log level |

## Run

```bash
# stdio (default)
PIHOLE_URL=http://localhost:8080 PIHOLE_API_PASSWORD=... uv run pihole-mcp-server

# HTTP / streamable-http
PIHOLE_URL=http://localhost:8080 PIHOLE_API_PASSWORD=... \
  FASTMCP_TRANSPORT=streamable-http FASTMCP_PORT=3100 \
  uv run pihole-mcp-server
```

## Docker

```bash
docker run --rm --network host -e PIHOLE_URL=http://127.0.0.1:8080 \
  -e PIHOLE_API_PASSWORD=... -e FASTMCP_TRANSPORT=streamable-http \
  -p 3100:3100 ghcr.io/basalto/pihole-mcp-server:latest
```

## Notes

- **v6 status enum**: blocked queries surface as `GRAVITY` (blocklist) or `REGEX`
  (regex list), never `BLOCKED`. Use `status=GRAVITY` (and optionally `REGEX`) to see
  blocked queries.
- **Domain filter**: exact match by default; use `*` wildcards (e.g. `*tiktok*`) for
  partial matches.
- **`set_blocking` mutates live config** — only call it when the user explicitly asked.

## License

Apache-2.0
