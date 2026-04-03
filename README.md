# SafeTravel

A travel safety assistant for Chicago that connects a React frontend to Claude (Anthropic) via a FastMCP server. Users ask natural-language questions; Claude picks the right tool; the MCP server executes it and returns structured results.

```
Browser → React UI → FastAPI backend → Claude API → MCP server → Tools
```

---

## Project Structure

```
Travel-Safe/
├── api.py                      # FastAPI HTTP backend (POST /query)
│
├── client/
│   ├── cli.py                  # CLI client (natural-language → tool calls)
│   └── llm_mcp_client.py       # Claude → MCP bridge (core logic)
│
├── server/
│   ├── mcp_server.py           # FastMCP server — registers all tools
│   ├── schemas/
│   │   └── models.py           # Pydantic input schemas (LocationInput, etc.)
│   ├── tools/
│   │   ├── crimes.py           # get_recent_crimes  (Chicago Open Data API)
│   │   ├── buses.py            # get_bus_status     (CTA Bus Tracker API)
│   │   ├── stops.py            # get_stops          (mock data)
│   │   ├── safety.py           # assess_route_safety
│   │   └── incidents.py        # report_incident    (appends to incidents.log)
│   └── data/
│       ├── crimes.json         # Fallback crime data
│       ├── buses.json          # Fallback bus data
│       ├── stops.json          # Bus stop data
│       └── incidents.log       # User-reported incidents (auto-created)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Full React UI (all components in one file)
│   │   └── index.css           # Tailwind CSS entry
│   ├── vite.config.js          # Vite config + /query proxy to :8000
│   └── package.json
│
├── tests/                      # Test suite
├── scripts/
│   └── convert_crimes_csv.py   # Converts CSV crime data → crimes.json
├── requirements.txt
└── .env                        # API keys (never committed)
```

---

## How It Works

1. **User** types a question in the React UI and clicks Ask.
2. **React** sends `POST /query { "query": "..." }` to Vite's dev server.
3. **Vite proxy** forwards the request to the FastAPI backend on port 8000.
4. **FastAPI (`api.py`)** calls `_ask_claude()` — sends the query to Claude with a system prompt listing available tools.
5. **Claude** responds with JSON: `{ "tool": "<name>", "arguments": { ... } }`.
6. **FastAPI** calls `_call_mcp_tool()` — spawns `python -m server.mcp_server` as a subprocess, performs the MCP initialize handshake over stdin/stdout, then sends a `tools/call` JSON-RPC request.
7. **MCP server** executes the tool (hitting the Chicago Open Data API or local mock data).
8. **Result** flows back: MCP → FastAPI → React → displayed in structured cards.

---

## Setup & Running

### Prerequisites

- Python 3.9+
- Node.js 18+
- An [Anthropic API key](https://console.anthropic.com/)
- (Optional) A [CTA Bus Tracker API key](https://www.transitchicago.com/developers/) for live bus data

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd Travel-Safe

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=sk-ant-...
CTA_API_KEY=your_cta_key_here   # optional — falls back to mock data
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 5. Start the Python backend

```bash
# From the project root, with venv active
python -m uvicorn api:app --port 8000 --reload
```

### 6. Start the React frontend

```bash
# In a second terminal
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

### CLI (optional, no frontend needed)

```bash
python -m client.cli query "Is route 22 safe from downtown to Lincoln Park?"
python -m client.cli query "Show crimes near Navy Pier"
python -m client.cli query "What buses are on route 36?"
python -m client.cli status
```

---

## Available Tools

| Tool | Description | Key Inputs |
|---|---|---|
| `get_recent_crimes_tool` | Crimes within ~1.5 km of a point | `lat`, `lon` |
| `get_bus_status_tool` | Live bus positions and delay status | `route` (e.g. `"Route 22"`) |
| `get_stops_tool` | All stops on a route | `route` |
| `assess_route_safety_tool` | Risk level + recommendation for a trip | `origin_lat/lon`, `dest_lat/lon`, optional `route` |
| `report_incident_tool` | Log a user-reported safety incident | `location` (`"lat,lon"`), `description` |

---

## How Are Unsafe or Destructive Actions Prevented?

**Input validation at every boundary.**
All tool inputs are parsed through Pydantic schemas (`LocationInput`, `RouteInput`, `IncidentReportInput`) before any logic runs. Invalid coordinates, empty strings, or wrong types are rejected before they reach the tools.

**Write operations are strictly isolated.**
The only write operation in the system is `report_incident`, which appends a single CSV line to `incidents.log`. It cannot overwrite, truncate, or delete the file. There is no tool that deletes data, modifies configuration, or executes shell commands.

**Claude is constrained by the system prompt.**
Claude is instructed to choose exactly one tool from a fixed list and return only a JSON object. It cannot invent new tools, chain calls, or execute free-form code. If its response is not valid JSON with a known tool name, the request is rejected before touching the MCP server.

**MCP subprocess is sandboxed by design.**
The MCP server is spawned as a short-lived child process per request. It has no persistent state, no network access beyond the two APIs it already calls, and is terminated immediately after the tool result is read.

**External API calls are read-only and rate-limited.**
The Chicago Open Data and CTA APIs are queried with a 5-second timeout and a result limit. Neither API accepts writes from this system.

---

## How Is Incorrect Agent Behavior Debugged?

**Step 1 — Inspect Claude's decision.**
Every API response includes `tool` and `arguments` fields showing exactly what Claude chose. The Query Flow card in the UI displays this. If Claude picks the wrong tool or wrong coordinates, this is immediately visible.

**Step 2 — Trace the MCP exchange.**
In `llm_mcp_client.py`, the commented-out debug prints (lines ~246-247) can be re-enabled to log the tool name and arguments to stdout. The MCP server's stderr is suppressed (`stderr=DEVNULL`) by default — redirect it to a file to see FastMCP's internal logs:

```python
# In _call_mcp_tool(), change:
stderr=subprocess.DEVNULL
# to:
stderr=open("mcp_debug.log", "w")
```

**Step 3 — Reproduce with the CLI.**
The CLI (`client/cli.py`) bypasses Claude entirely and calls tools directly with explicit inputs. This isolates whether a problem is in Claude's decision or in the tool logic itself:

```bash
python -m client.cli query "crimes at 41.8781 -87.6298"
```

**Step 4 — Check the data source.**
If a tool returns unexpected results, check whether it hit the live API or fell back to mock data. Both `crimes.py` and `buses.py` fall back silently — add a temporary `print` in `_fetch_crimes_from_api` / `_fetch_buses_from_api` to confirm which path was taken.

**Step 5 — Unit test the tool directly.**
Each tool function accepts plain Pydantic models and can be called in isolation from a Python REPL or test:

```python
from server.tools import get_recent_crimes
from server.schemas.models import LocationInput
crimes = get_recent_crimes(LocationInput(latitude=41.8781, longitude=-87.6298))
```

---

## What Metrics Matter in Production?

**Latency**
- `Claude API response time` — typically the longest step (~1–3 s). Track p50/p95.
- `MCP tool execution time` — subprocess spawn + tool run. Should be under 2 s for mock data, up to 6 s when hitting live APIs with timeout.
- `End-to-end request time` — sum of the above. Target under 8 s for acceptable UX.

**Reliability**
- `Claude JSON parse failure rate` — how often Claude returns malformed JSON or picks an unknown tool. A non-zero rate here means the system prompt needs tightening.
- `MCP tool error rate` — `isError: true` responses from the MCP server. Indicates tool logic failures (bad coordinates, API outages).
- `External API fallback rate` — how often `crimes.py` / `buses.py` fall back to mock data. High rates mean the live APIs are unreliable or the API key is invalid.

**Safety**
- `Invalid input rejection rate` — how often Pydantic validation rejects a request. Useful for detecting prompt injection attempts or malformed queries.
- `report_incident write errors` — failed writes to `incidents.log` (permissions, disk space).

**Cost**
- `Claude API tokens per request` — the system prompt is ~150 tokens; user queries add ~20–50. Monitor for token creep if the system prompt grows.

---

## Data Sources

| Data | Source | Fallback |
|---|---|---|
| Crime incidents | [Chicago Open Data API](https://data.cityofchicago.org/resource/x2n5-8w5q.json) | `server/data/crimes.json` |
| Bus positions | [CTA Bus Tracker API](https://www.transitchicago.com/developers/) | `server/data/buses.json` |
| Bus stops | Local mock | `server/data/stops.json` |
| User incidents | Local log | — (appended on report) |
