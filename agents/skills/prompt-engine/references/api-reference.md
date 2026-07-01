# Prompt Engine API Reference

## REST API (FastAPI)

Base URL: `http://localhost:8013`

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/optimize` | Optimize a prompt |
| POST | `/v1/classify` | Classify prompt style |
| GET | `/v1/styles/categories` | List 25 style dimensions |
| POST | `/v1/feedback` | Submit classification feedback |
| GET | `/v1/feedback/stats` | Feedback statistics |
| GET | `/v1/feedback/recent` | Recent feedback entries |
| POST | `/v1/feedback/apply` | Apply feedback to weights |
| POST | `/v1/reverse` | Reverse engineer image |
| POST | `/v1/batch` | Batch optimize |
| POST | `/v1/rewrite` | Rewrite short prompt |
| POST | `/v1/disturb-optimize` | Perturbation optimization |
| GET | `/v1/platforms` | List supported platforms |

### MCP Server

MCP server at `examples/start_mcp_server.py` exposes tools:
- `optimize_prompt`
- `classify_style`
- `list_style_categories`
