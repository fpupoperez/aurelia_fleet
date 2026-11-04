# MCP

FastMCP server. Each tool is one API `operationId` and calls the HTTP API. It does not open Postgres or embed anything.

The package directory is named `mcp`, which would hide the installed MCP SDK. `server.py` removes this directory and the repo root from `sys.path` before importing `mcp.server.fastmcp`, then puts `backend/` on the path so it can share telemetry settings. Ruff ignores E402 here on purpose.

| Variable | Default |
| --- | --- |
| `API_BASE_URL` | `http://localhost:8000/api/v1` |
| `MCP_HOST` | `0.0.0.0` |
| `MCP_PORT` | `8001` |

```bash
PYTHONPATH=backend python mcp/server.py
```

Compose publishes port 8001 and sets `API_BASE_URL=http://api:8000/api/v1`. Tool arguments come from the OpenAPI schema. File download is not a JSON envelope. Upload sends base64 and a metadata object. `equipmentModel` and `title` may be omitted. The API reads them from the file.
