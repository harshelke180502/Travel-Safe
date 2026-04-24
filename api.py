"""
HTTP backend for SafeTravel.

Exposes POST /query — the single endpoint the React frontend calls.
Receives a natural-language query, delegates to query_llm(), returns JSON.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


app = FastAPI(title="SafeTravel API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


class QueryRequest(BaseModel):
    query: str


@app.post("/query")
def handle_query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        from client.llm_mcp_client import _ask_claude, _call_mcp_tool, _clean_mcp_result

        # Step 1: Claude returns an ordered list of tool calls
        steps = _ask_claude(req.query)

        # Step 2: Execute each tool in sequence, collect results
        results = []
        for step in steps:
            raw = _call_mcp_tool(step["tool"], step["arguments"])
            results.append({
                "tool": step["tool"],
                "arguments": step["arguments"],
                "result": _clean_mcp_result(raw),
            })

        return {"steps": results}

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(exc)}")
