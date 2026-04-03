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
]

SYSTEM_PROMPT = """You are a travel safety assistant for Chicago.

You must choose EXACTLY ONE tool from the list below and return ONLY a JSON object.
Do not include any explanation, markdown, or extra text — just the raw JSON.

Available tools:
- get_recent_crimes_tool     : requires arguments: lat (float), lon (float)
- get_bus_status_tool        : requires arguments: route (str, e.g. "Route 22")
- get_stops_tool             : requires arguments: route (str, e.g. "Route 36")
- assess_route_safety_tool   : requires arguments: origin_lat (float), origin_lon (float), dest_lat (float), dest_lon (float), route (str, optional)
- report_incident_tool       : requires arguments: location (str, "lat,lon"), description (str)

Response format (strict):
{
  "tool": "<tool_name>",
  "arguments": { ... }
}"""

MCP_TIMEOUT = 15  # seconds to wait for MCP response


# ---------------------------------------------------------------------------
# Step 1 – Ask Claude which tool to call
# ---------------------------------------------------------------------------

def _ask_claude(user_query: str) -> dict:
    """
    Send user_query to Claude and parse its JSON tool-selection response.

    Returns:
        dict with keys "tool" and "arguments"

    Raises:
        ValueError: if Claude returns invalid JSON or missing keys
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
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

    if "tool" not in parsed or "arguments" not in parsed:
        raise ValueError(f"Claude JSON missing 'tool' or 'arguments' keys: {parsed}")

    if parsed["tool"] not in MCP_TOOL_NAMES:
        raise ValueError(
            f"Claude chose unknown tool '{parsed['tool']}'. "
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
        stderr=subprocess.DEVNULL,  # suppress server debug output
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
    # Step 1: Claude decides which tool to call
    claude_decision = _ask_claude(user_query)
    tool_name = claude_decision["tool"]
    arguments = claude_decision["arguments"]

    print(f"[llm_mcp_client] Claude selected: {tool_name}")
    print(f"[llm_mcp_client] Arguments:       {json.dumps(arguments)}")

    # Step 2: MCP server executes the tool
    result = _call_mcp_tool(tool_name, arguments)    
    return _clean_mcp_result(result)


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
