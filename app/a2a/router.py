from __future__ import annotations

from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings


logger = structlog.get_logger("a2a")
router = APIRouter()


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None


class JSONRPCRequest(BaseModel):
    jsonrpc: str = Field(alias="jsonrpc")
    id: Optional[str | int] = None
    method: str
    params: Optional[Dict[str, Any]] = None


class JSONRPCResult(BaseModel):
    status: str = "success"
    summary: Optional[str] = None
    artifacts: Optional[list[Dict[str, Any]]] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str | int] = None
    result: Optional[JSONRPCResult] = None
    error: Optional[JSONRPCError] = None


def _method_not_implemented(id_: Optional[str | int], method: str) -> JSONRPCResponse:
    return JSONRPCResponse(
        id=id_,
        error=JSONRPCError(code=-32601, message=f"Method '{method}' not implemented"),
    )


@router.post("/a2a/agent/{agent_name}")
async def a2a_endpoint(request: Request, agent_name: str) -> JSONResponse:  # type: ignore[no-untyped-def]
    """Generic A2A JSON-RPC endpoint that validates method and returns a JSON-RPC response.

    Stage 1: only 'status' is implemented; others return -32601.
    """
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        req = JSONRPCRequest.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("jsonrpc.invalid_request", error=str(exc))
        return JSONResponse(
            status_code=200,
            content=JSONRPCResponse(
                id=payload.get("id"),
                error=JSONRPCError(code=-32600, message="Invalid Request"),
            ).model_dump(),
        )

    if req.jsonrpc != "2.0":
        return JSONResponse(
            status_code=200,
            content=JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32600, message="Invalid Request: jsonrpc must be '2.0'"
                ),
            ).model_dump(),
        )

    # Implement only 'status' for Stage 1
    if req.method == "status":
        settings = get_settings()
        result = JSONRPCResult(
            status="success",
            summary="Service is healthy",
            artifacts=[
                {
                    "kind": "meta",
                    "data": {
                        "agent": agent_name,
                        "configured_agent": settings.A2A_AGENT_NAME,
                        "env": settings.ENV,
                    },
                }
            ],
        )
        resp = JSONRPCResponse(id=req.id, result=result)
        logger.info("jsonrpc.status", id=req.id, agent=agent_name)
        return JSONResponse(status_code=200, content=resp.model_dump())

    # For message/send and execute (and anything else), respond as not implemented
    not_impl = _method_not_implemented(req.id, req.method)
    logger.info("jsonrpc.not_implemented", method=req.method, id=req.id)
    return JSONResponse(status_code=200, content=not_impl.model_dump())


@router.post("/a2a/agent/bankMatcher")
async def a2a_endpoint_fixed(request: Request) -> JSONResponse:  # type: ignore[no-untyped-def]
    """Fixed route to match documentation examples."""
    return await a2a_endpoint(request, agent_name=get_settings().A2A_AGENT_NAME)
