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
print(os.getenv("ANTHROPIC_API_KEY"))


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

        # Step 1: Claude picks tool + arguments
        decision = _ask_claude(req.query)
        tool = decision["tool"]
        arguments = decision["arguments"]

        # Step 2: MCP server executes the tool
        raw = _call_mcp_tool(tool, arguments)

        # Step 3: Unwrap MCP envelope { content: [{type, text}], isError }
        result = _clean_mcp_result(raw)

        return {"tool": tool, "arguments": arguments, "result": result}

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(exc)}")
