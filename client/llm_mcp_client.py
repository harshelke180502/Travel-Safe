"""
LLM MCP client for SafeTravel.

Bridges Claude (Anthropic) and the SafeTravel MCP server:
  User query → Claude picks tool + args → MCP server executes → result returned.
"""

import json
import os
import subprocess
import sys
import time
from typing import Any
from dotenv import load_dotenv
import os

load_dotenv()

import anthropic

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCP_TOOL_NAMES = [
    "get_recent_crimes_tool",
    "get_bus_status_tool",
    "get_stops_tool",
    "assess_route_safety_tool",
    "report_incident_tool",
    "get_incidents_tool",
]

SYSTEM_PROMPT = """You are a travel safety assistant for Chicago.

Choose one or more tools based on what the query needs and call them in logical order.
Return ONLY a JSON array — no explanation, no markdown, just raw JSON.

Tool selection rules:
- get_stops_tool         → bus stop locations on a route
- get_bus_status_tool    → live bus positions and delay status on a route
- report_incident_tool   → WRITE: user wants to submit/report a new safety incident
- get_incidents_tool     → READ: user wants to see all reported incidents from the database
- get_recent_crimes_tool → crime data near a specific coordinate
- assess_route_safety_tool → overall route safety score between two locations

Multi-tool rules:
- "Get bus stops and show incidents nearby" → [get_stops_tool, get_incidents_tool]
- "Report hazard and show recent incidents" → [report_incident_tool, get_incidents_tool]
- "Is route 22 safe and show live buses"   → [assess_route_safety_tool, get_bus_status_tool]

Available tools and their arguments:
- get_recent_crimes_tool    : location (str, "lat,lon" OR place name e.g. "UIC", "Pilsen", "Michigan Avenue")
- get_bus_status_tool       : route (str, e.g. "Route 22")
- get_stops_tool            : route (str, e.g. "Route 36")
- assess_route_safety_tool  : origin_lat (float), origin_lon (float), dest_lat (float), dest_lon (float), route (str, optional)
- report_incident_tool      : location (str, "lat,lon" OR place name e.g. "UIC", "N LaSalle St"), description (str)
- get_incidents_tool        : no arguments

Response format (always an array, even for a single tool):
[
  { "tool": "<tool_name>", "arguments": { ... } }
]"""

MCP_TIMEOUT = 15  # seconds to wait for MCP response


# ---------------------------------------------------------------------------
# Step 1 – Ask Claude which tool to call
# ---------------------------------------------------------------------------

def _ask_claude(user_query: str) -> list:
    """
    Send user_query to Claude and parse its JSON array of tool calls.

    Returns:
        List of dicts, each with keys "tool" and "arguments"

    Raises:
        ValueError: if Claude returns invalid JSON or an unknown tool name
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_query}],
    )

    raw = message.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude returned invalid JSON: {exc}\nRaw response: {raw}") from exc

    # Normalise: wrap a bare single-object response in a list
    if isinstance(parsed, dict):
        parsed = [parsed]

    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f"Claude response must be a non-empty JSON array: {parsed}")

    for step in parsed:
        if "tool" not in step or "arguments" not in step:
            raise ValueError(f"Tool call missing 'tool' or 'arguments': {step}")
        if step["tool"] not in MCP_TOOL_NAMES:
            raise ValueError(
                f"Claude chose unknown tool '{step['tool']}'. "
                f"Valid tools: {MCP_TOOL_NAMES}"
            )

    return parsed


# ---------------------------------------------------------------------------
# Step 2 – Send the tool call to the MCP server via subprocess + stdio
# ---------------------------------------------------------------------------

def _mcp_initialize(proc: subprocess.Popen, req_id: int) -> None:
    """
    Perform the MCP initialize handshake (required before any tool call).

    Sends `initialize` request and `initialized` notification per MCP spec.
    """
    init_request = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "llm-mcp-client", "version": "1.0"},
        },
        "id": req_id,
    }
    _send_message(proc, init_request)
    _read_response(proc)  # consume initialize response

    initialized_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    _send_message(proc, initialized_notification)


def _send_message(proc: subprocess.Popen, payload: dict) -> None:
    """Write a newline-delimited JSON message to the subprocess stdin."""
    line = json.dumps(payload) + "\n"
    proc.stdin.write(line.encode())
    proc.stdin.flush()


def _read_response(proc: subprocess.Popen, timeout: float = MCP_TIMEOUT) -> dict:
    """
    Read one newline-delimited JSON response from the subprocess stdout.

    Raises:
        TimeoutError: if no response arrives within `timeout` seconds
        RuntimeError: if the process exits unexpectedly
        ValueError: if the response is not valid JSON
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        # Check if process died
        if proc.poll() is not None:
            raise RuntimeError(
                f"MCP server process exited with code {proc.returncode}"
            )

        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue

        line = line.decode().strip()
        if not line:
            continue

        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"MCP returned invalid JSON: {exc}\nRaw line: {line}") from exc

    raise TimeoutError(
        f"MCP server did not respond within {timeout}s"
    )


def _call_mcp_tool(tool_name: str, arguments: dict) -> Any:
    """
    Start the MCP server as a subprocess, perform the handshake,
    call the tool, and return the result.

    Raises:
        RuntimeError: on MCP-level errors
        TimeoutError: if the server is unresponsive
    """
    proc = subprocess.Popen(
        [sys.executable, "-m", "server.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,  # forward MCP subprocess debug output to terminal
    )

    try:
        _mcp_initialize(proc, req_id=0)

        tool_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
            "id": 1,
        }
        _send_message(proc, tool_request)
        response = _read_response(proc)
    finally:
        proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    # Surface JSON-RPC errors
    if "error" in response:
        err = response["error"]
        raise RuntimeError(
            f"MCP error {err.get('code')}: {err.get('message')}"
        )

    return response.get("result")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _clean_mcp_result(result):
        if not result or "content" not in result:
            return result

        cleaned = []

        for item in result["content"]:
            if item.get("type") == "text":
                text = item.get("text", "").strip()

                try:
                    parsed = json.loads(text)
                    cleaned.append(parsed)
                except:
                    cleaned.append(text)

        return cleaned

def query_llm(user_query: str) -> Any:
    """
    Execute a full User → Claude → MCP → result round trip.

    Args:
        user_query: Natural language question or instruction.

    Returns:
        The tool result from the MCP server (dict or list).

    Raises:
        ValueError: if Claude returns unparseable JSON or picks an unknown tool.
        RuntimeError: if the MCP server returns an error.
        TimeoutError: if the MCP server is unresponsive.
    """
    # Step 1: Claude decides which tools to call
    steps = _ask_claude(user_query)

    # Step 2: Execute each tool in sequence
    results = []
    for step in steps:
        tool_name = step["tool"]
        arguments = step["arguments"]
        print(f"[llm_mcp_client] Claude selected: {tool_name}")
        print(f"[llm_mcp_client] Arguments:       {json.dumps(arguments)}")
        raw = _call_mcp_tool(tool_name, arguments)
        results.append({
            "tool": tool_name,
            "arguments": arguments,
            "result": _clean_mcp_result(raw),
        })

    return results


# ---------------------------------------------------------------------------
# CLI entry point (for quick manual testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m client.llm_mcp_client \"<query>\"")
        sys.exit(1)

    user_input = " ".join(sys.argv[1:])
    print(f"\nQuery: {user_input}\n")

    try:
        output = query_llm(user_input)
        print("\nResult:")
        print(json.dumps(output, indent=2, default=str))
    except (ValueError, RuntimeError, TimeoutError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)
