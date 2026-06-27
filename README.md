# Unsplash MCP Server

An MCP (Model Context Protocol) server for searching and retrieving photos from [Unsplash](https://unsplash.com) with built-in, ready-to-use attribution strings.

## Tools

| Tool | Description |
|------|-------------|
| `search_photos` | Search photos by keyword with optional filters (color, orientation, safety) |
| `get_random_photos` | Fetch random photos, optionally filtered by keyword |
| `track_download` | Record a download event (required by Unsplash API guidelines) |

Every photo response includes `attribution_text` and `attribution_html` — pre-built credit strings that satisfy Unsplash's attribution requirement without any URL construction on your end.

## Prerequisites

- Python 3.11+
- An Unsplash API access key — [register a free app at unsplash.com/developers](https://unsplash.com/developers)

> **Important:** When registering your Unsplash app, set the **Application name** to `unsplash_mcp`. This must match the `utm_source` value used in the server.

## Installation

```bash
git clone https://github.com/ninavolu/unsplash-mcp.git
cd unsplash-mcp

python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install fastmcp httpx python-dotenv

# Create a .env file with your key
echo "UNSPLASH_ACCESS_KEY=your_key_here" > .env

# Verify it starts
fastmcp run server.py
```

## Configuration

### Hosted (remote connector)

The server speaks Streamable HTTP, so it can be deployed once and added as a
custom connector by URL — no local install or per-user API key. Deploy it
(see [Deployment](#deployment)) and add the URL in Claude:

- **Claude.ai / Claude Code** → Settings → Connectors → *Add custom connector* →
  `https://your-deployment.example.com/mcp`

The Unsplash access key lives only on the server (set as the `UNSPLASH_ACCESS_KEY`
environment variable); clients never see it.

### Claude (claude.ai / Claude Code) — local stdio

Add to `~/.claude.json` or your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "unsplash": {
      "type": "stdio",
      "command": "/path/to/unsplash-mcp/.venv/bin/fastmcp",
      "args": ["run", "/path/to/unsplash-mcp/server.py"],
      "env": {
        "UNSPLASH_ACCESS_KEY": "your_access_key_here"
      }
    }
  }
}
```

### Cursor / Windsurf / Cline

```json
{
  "mcpServers": {
    "unsplash": {
      "command": "/path/to/unsplash-mcp/.venv/bin/fastmcp",
      "args": ["run", "/path/to/unsplash-mcp/server.py"],
      "env": {
        "UNSPLASH_ACCESS_KEY": "your_access_key_here"
      }
    }
  }
}
```

## Photo Response Shape

```python
{
    "id": "abc123",
    "description": "A mountain lake at sunrise",
    "alt_description": "calm body of water near mountain",
    "urls": {
        "raw": "https://images.unsplash.com/...",
        "full": "https://images.unsplash.com/...",
        "regular": "https://images.unsplash.com/...",  # best for web
        "small": "https://images.unsplash.com/...",
        "thumb": "https://images.unsplash.com/..."
    },
    "width": 5184,
    "height": 3456,
    "color": "#a3b4c5",
    "blur_hash": "LKO2?U%2...",
    "photographer_name": "Jane Smith",
    "photographer_username": "janesmith",
    "photographer_url": "https://unsplash.com/@janesmith?utm_source=unsplash_mcp&utm_medium=referral",
    "photo_url": "https://unsplash.com/photos/abc123?utm_source=unsplash_mcp&utm_medium=referral",
    "attribution_text": "Photo by Jane Smith on Unsplash",
    "attribution_html": "Photo by <a href=\"...\">Jane Smith</a> on <a href=\"...\">Unsplash</a>"
}
```

## Unsplash API Compliance

This server handles all three Unsplash API requirements automatically:

1. **Attribution** — every response includes `attribution_html` with proper links
2. **Hotlinking** — uses Unsplash CDN URLs directly (enables their view tracking)
3. **Download tracking** — call `track_download(photo_id)` when a user saves an image

## Rate Limits

| Mode | Limit |
|------|-------|
| Demo (default) | 50 requests / hour |
| Production (apply at unsplash.com) | 5,000 requests / hour |

The hosted server also applies a per-IP cap (30 requests/hour by default,
configurable in `server.py`) to protect the shared Unsplash key.

## Deployment

Any platform that runs Python and exposes a port works. A `Procfile` and
`railway.json` are included for [Railway](https://railway.app):

1. Create a new project from this repo.
2. Set the `UNSPLASH_ACCESS_KEY` environment variable.
3. Deploy — the server listens on `$PORT` and serves MCP at `/mcp`.

`GET /health` returns `{"status": "ok"}` for platform health checks.

## Privacy & Data

This server only forwards the search/query parameters you pass to the Unsplash
API and returns the results. It does **not** read or store conversation history,
chat content, memory, or user files, and it collects no analytics beyond
Unsplash's own view/download tracking (required by their API guidelines). The
Unsplash access key is held server-side and never exposed to clients.

## License

MIT — see [LICENSE](LICENSE).
