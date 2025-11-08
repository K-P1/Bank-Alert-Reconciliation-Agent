from __future__ import annotations

from typing import Any, Dict, Optional, List

import structlog
from fastapi import APIRouter, HTTPException, Depends
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.base import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.matching.engine import match_unmatched, MatchingEngine
from app.db.repositories.email_repository import EmailRepository
from app.db.repositories.match_repository import MatchRepository
from app.db.models.email import Email
from app.db.models.match import Match
from app.matching.models import MatchResult, BatchMatchResult
from app.a2a.command_interpreter import get_interpreter
from app.a2a.command_handlers import (
    CommandHandlers,
    extract_limit,
    extract_days,
    extract_rematch_flag,
)


logger = structlog.get_logger("a2a")
router = APIRouter()


# Initialize command interpreter on module load
def _init_command_interpreter() -> None:
    """Initialize the command interpreter with all supported commands."""
    interpreter = get_interpreter()

    # Register: reconcile_now
    interpreter.register_command(
        name="reconcile_now",
        patterns=[
            r"\breconcile\b",
            r"\brun\s+(the\s+)?reconciliation\b",
            r"\bmatch\s+(emails?|alerts?)\b",
            r"\bstart\s+matching\b",
            r"\bprocess\s+(emails?|alerts?)\b",
        ],
        handler=None,  # Will be set at runtime with db session
        description="Run reconciliation immediately to match bank alerts with transactions",
        examples=[
            "run reconciliation",
            "reconcile now",
            "match 50 emails",
            "process alerts",
        ],
        param_extractors={"limit": extract_limit, "rematch": extract_rematch_flag},
    )

    # Register: show_summary
    interpreter.register_command(
        name="show_summary",
        patterns=[
            r"\bshow\s+(me\s+)?(the\s+)?summary\b",
            r"\b(get|give)\s+(me\s+)?(the\s+)?status\b",
            r"\bwhat.?s\s+the\s+status\b",
            r"\boverview\b",
            r"\bdashboard\b",
        ],
        handler=None,
        description="Display summary of matched and unmatched emails",
        examples=[
            "show summary",
            "give me the status",
            "what's the status",
            "show me the overview",
        ],
        param_extractors={"days": extract_days},
    )

    # Register: list_unmatched
    interpreter.register_command(
        name="list_unmatched",
        patterns=[
            r"\blist\s+unmatched\b",
            r"\bshow\s+(me\s+)?(the\s+)?unmatched\b",
            r"\bpending\s+(emails?|alerts?)\b",
            r"\bwhat.?s\s+unmatched\b",
            r"\bunpaired\b",
        ],
        handler=None,
        description="List all unmatched email alerts",
        examples=[
            "list unmatched",
            "show unmatched emails",
            "pending alerts",
            "what's unmatched",
        ],
        param_extractors={"limit": extract_limit},
    )

    # Register: get_confidence_report
    interpreter.register_command(
        name="get_confidence_report",
        patterns=[
            r"\bconfidence\s+report\b",
            r"\baccuracy\s+(report|stats?)\b",
            r"\bshow\s+(me\s+)?(the\s+)?metrics\b",
            r"\bhow\s+(accurate|well)\b",
            r"\bperformance\s+report\b",
        ],
        handler=None,
        description="Generate confidence and accuracy report for recent matches",
        examples=[
            "get confidence report",
            "show accuracy stats",
            "how accurate are we",
            "performance report",
        ],
        param_extractors={"days": extract_days},
    )

    # Register: help
    interpreter.register_command(
        name="help",
        patterns=[
            r"\bhelp\b",
            r"\bcommands?\b",
            r"\bwhat\s+can\s+you\s+do\b",
            r"\binstructions?\b",
            r"\bhow\s+to\s+use\b",
        ],
        handler=None,
        description="Show list of available commands",
        examples=["help", "show commands", "what can you do"],
    )

    logger.info("command_interpreter.initialized", command_count=len(interpreter.commands))


# Initialize on module load
_init_command_interpreter()


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


# Telex A2A Protocol Models
class MessagePart(BaseModel):
    """A part of a message (text, data, artifact, etc.)"""
    kind: str  # "text", "data", "artifact", etc.
    text: Optional[str] = None
    data: Optional[Any] = None
    mimeType: Optional[str] = None


class Message(BaseModel):
    """A message response conforming to Telex A2A protocol"""
    kind: str = "message"
    role: str = "agent"  # Telex expects "agent" not "assistant"
    parts: List[MessagePart]
    metadata: Optional[Dict[str, Any]] = None


class TaskStatus(BaseModel):
    """Status of an async task"""
    state: str  # "pending", "running", "completed", "failed"
    progress: Optional[float] = None
    message: Optional[str] = None


class Task(BaseModel):
    """An async task response conforming to Telex A2A protocol"""
    id: str
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None


# Union type for result field
JSONRPCResult = Message | Task


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
async def a2a_endpoint(request: Request, agent_name: str, db: AsyncSession = Depends(get_db)) -> JSONResponse:  # type: ignore[no-untyped-def]
    """Generic A2A JSON-RPC endpoint that validates method and returns a JSON-RPC response.

    Supported methods:
    - status: Health check and service information
    - message/send: Synchronous reconciliation of bank alert emails
    - execute: Async job submission (placeholder for future implementation)
    """
    logger.info("a2a.request.received", agent_name=agent_name, path=str(request.url.path))
    
    try:
        # Parse JSON body
        payload = await request.json()
        logger.debug("a2a.request.parsed", payload_keys=list(payload.keys()))
    except Exception as exc:  # noqa: BLE001
        logger.error("a2a.request.invalid_json", error=str(exc))
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        # Validate JSON-RPC request
        req = JSONRPCRequest.model_validate(payload)
        logger.info("a2a.request.validated", method=req.method, request_id=req.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("a2a.request.validation_failed", error=str(exc), payload=payload)
        return JSONResponse(
            status_code=200,
            content=JSONRPCResponse(
                id=payload.get("id"),
                error=JSONRPCError(code=-32600, message="Invalid Request"),
            ).model_dump(),
        )

    # Validate jsonrpc version
    if req.jsonrpc != "2.0":
        logger.warning("a2a.request.wrong_version", version=req.jsonrpc, expected="2.0")
        return JSONResponse(
            status_code=200,
            content=JSONRPCResponse(
                id=req.id,
                error=JSONRPCError(
                    code=-32600, message="Invalid Request: jsonrpc must be '2.0'"
                ),
            ).model_dump(),
        )

    # NATURAL LANGUAGE COMMAND INTERPRETATION ---------------------------------------
    # Check if this is a natural language message (message/send with text content)
    if req.method == "message/send" and req.params:
        message_obj = req.params.get("message", {})
        if isinstance(message_obj, dict):
            # Interpret the command
            interpreter = get_interpreter()
            # Use robust extraction for user text
            user_text = interpreter.extract_text(req.model_dump())
            if user_text:
                logger.info("a2a.natural_language.detected", text_length=len(user_text))
                command_match = interpreter.interpret(user_text)
                logger.info(
                    "a2a.natural_language.interpreted",
                    command=command_match.command_name,
                    confidence=command_match.confidence,
                )
                # Handle help command specially
                if command_match.command_name == "help":
                    help_text = interpreter.get_help_text()
                    result = Message(
                        parts=[
                            MessagePart(kind="text", text=help_text),
                            MessagePart(
                                kind="data",
                                data={
                                    "commands": list(interpreter.commands.keys()),
                                    "reason": command_match.params.get("reason"),
                                    "interpreted_from": user_text,
                                }
                            )
                        ]
                    )
                    resp = JSONRPCResponse(id=req.id, result=result)
                    return JSONResponse(status_code=200, content=resp.model_dump())
                # Execute the matched command
                try:
                    handlers = CommandHandlers(db)
                    handler_method = getattr(handlers, command_match.command_name)
                    result_data = await handler_method(command_match.params)
                    
                    # Build message parts
                    message_parts = []
                    
                    # Add summary as text
                    if result_data.get("summary"):
                        message_parts.append(MessagePart(kind="text", text=result_data["summary"]))
                    
                    # Add artifacts as data
                    if result_data.get("artifacts"):
                        message_parts.append(MessagePart(kind="data", data=result_data["artifacts"]))
                    
                    # Add metadata
                    metadata = {
                        **result_data.get("meta", {}),
                        "interpreted_from": user_text,
                        "command": command_match.command_name,
                        "confidence": command_match.confidence,
                        "status": result_data.get("status", "success"),
                    }
                    
                    result = Message(
                        parts=message_parts,
                        metadata=metadata
                    )
                    resp = JSONRPCResponse(id=req.id, result=result)
                    logger.info(
                        "a2a.natural_language.success",
                        command=command_match.command_name,
                        status=result_data.get("status"),
                    )
                    return JSONResponse(status_code=200, content=resp.model_dump())
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "a2a.natural_language.error",
                        command=command_match.command_name,
                        error=str(exc),
                    )
                    return JSONResponse(
                        status_code=200,
                        content=JSONRPCResponse(
                            id=req.id,
                            error=JSONRPCError(
                                code=500,
                                message=f"Command execution failed: {command_match.command_name}",
                                data={"detail": str(exc)},
                            ),
                        ).model_dump(),
                    )

    # STATUS METHOD -----------------------------------------------------------------
    if req.method == "status":
        logger.info("a2a.status.start", request_id=req.id, agent=agent_name)
        settings = get_settings()
        
        status_text = f"🟢 **BARA Service is healthy**\n\n"
        status_text += f"**Agent:** {agent_name}\n"
        status_text += f"**Environment:** {settings.ENV}\n"
        status_text += f"**Configured Agent:** {settings.A2A_AGENT_NAME}\n"
        
        result = Message(
            parts=[
                MessagePart(kind="text", text=status_text),
                MessagePart(
                    kind="data",
                    data={
                        "agent": agent_name,
                        "configured_agent": settings.A2A_AGENT_NAME,
                        "env": settings.ENV,
                    }
                )
            ]
        )
        resp = JSONRPCResponse(id=req.id, result=result)
        logger.info("a2a.status.success", request_id=req.id, agent=agent_name, env=settings.ENV)
        return JSONResponse(status_code=200, content=resp.model_dump())

    # MESSAGE/SEND (ON-DEMAND RECONCILIATION) ---------------------------------------
    if req.method == "message/send":
        # Parameters contract:
        # params: { limit?: int, rematch?: bool, email_ids?: [int], summarize?: bool }
        params = req.params or {}
        limit = params.get("limit")
        email_ids: List[int] | None = params.get("email_ids")
        rematch: bool = bool(params.get("rematch", False))
        summarize: bool = bool(params.get("summarize", True))

        logger.info(
            "a2a.reconcile.start",
            request_id=req.id,
            limit=limit,
            email_ids_count=len(email_ids) if email_ids else 0,
            rematch=rematch,
            summarize=summarize
        )

        try:
            batch_result: BatchMatchResult

            if email_ids:
                # Explicit set of emails provided
                logger.info("a2a.reconcile.mode.targeted", email_ids=email_ids, count=len(email_ids))
                engine = MatchingEngine(db)
                match_repo = MatchRepository(Match, db)
                results: List[MatchResult] = []
                for eid in email_ids:
                    logger.debug("a2a.reconcile.processing_email", email_id=eid, rematch=rematch)
                    if rematch:
                        res = await engine.rematch_email(eid)
                        logger.info("a2a.reconcile.email_rematched", email_id=eid, status=res.match_status)
                    else:
                        # Fetch email and match only if no existing match
                        repo = EmailRepository(Email, db)
                        email_model = await repo.get_by_id(eid)
                        if not email_model:
                            # Skip non-existent email IDs
                            logger.warning("a2a.reconcile.email_not_found", email_id=eid, request_id=req.id)
                            continue
                        # Check if match already exists using repository
                        if await match_repo.exists_for_email(eid):
                            logger.debug("a2a.reconcile.email_already_matched", email_id=eid)
                            continue
                        res = await engine.rematch_email(eid)
                        logger.info("a2a.reconcile.email_matched", email_id=eid, status=res.match_status)
                    results.append(res)
                # Build synthetic batch result
                from app.matching.models import BatchMatchResult as BMR
                batch_result = BMR()
                for r in results:
                    batch_result.add_result(r)
                batch_result.finalize()
                logger.info("a2a.reconcile.targeted_complete", emails_processed=len(results))
            else:
                # Match all currently unmatched (respect limit)
                logger.info("a2a.reconcile.mode.unmatched", limit=limit)
                batch_result = await match_unmatched(db, limit=limit)
                logger.info("a2a.reconcile.unmatched_complete", emails_processed=batch_result.total_emails)

            # Build artifacts
            result_artifacts: list[Dict[str, Any]] = []
            for r in batch_result.results:
                artifact = {
                    "kind": "reconciliation_result",
                    "data": {
                        "email_id": r.email_id,
                        "email_message_id": r.email_message_id,
                        "matched": r.matched,
                        "confidence": r.confidence,
                        "status": r.match_status,
                        "best_candidate": (
                            {
                                "transaction_id": r.best_candidate.transaction_id,
                                "external_transaction_id": r.best_candidate.external_transaction_id,
                                "score": r.best_candidate.total_score,
                                "rule_scores": [
                                    {
                                        "rule": rs.rule_name,
                                        "score": rs.score,
                                        "weight": rs.weight,
                                        "weighted": rs.weighted_score,
                                        "details": rs.details,
                                    }
                                    for rs in r.best_candidate.rule_scores
                                ],
                            }
                            if r.best_candidate
                            else None
                        ),
                        "alternatives": [
                            {
                                "transaction_id": c.transaction_id,
                                "external_transaction_id": c.external_transaction_id,
                                "score": c.total_score,
                                "rank": c.rank,
                            }
                            for c in r.alternative_candidates
                        ],
                        "notes": r.notes,
                    },
                }
                result_artifacts.append(artifact)

            summary_text = None
            if summarize:
                summary_text = (
                    f"✅ **Reconciliation complete!**\n\n"
                    f"📊 **Results:**\n"
                    f"  • Total processed: {batch_result.total_emails}\n"
                    f"  • Auto-matched: {batch_result.total_matched}\n"
                    f"  • Needs review: {batch_result.total_needs_review}\n"
                    f"  • Rejected: {batch_result.total_rejected}\n"
                    f"  • No candidates: {batch_result.total_no_candidates}\n"
                    f"  • Avg confidence: {batch_result.average_confidence:.2%}\n"
                )

            # Build message parts
            message_parts = []
            if summary_text:
                message_parts.append(MessagePart(kind="text", text=summary_text))
            
            # Add artifacts as structured data
            if result_artifacts:
                message_parts.append(MessagePart(kind="data", data=result_artifacts))
            
            # Create metadata
            metadata = {
                "batch": batch_result.get_summary(),
                "params": {"limit": limit, "email_ids": email_ids, "rematch": rematch},
            }
            
            result = Message(
                parts=message_parts,
                metadata=metadata
            )
            resp = JSONRPCResponse(id=req.id, result=result)
            logger.info(
                "a2a.reconcile.success",
                request_id=req.id,
                emails=batch_result.total_emails,
                matched=batch_result.total_matched,
                needs_review=batch_result.total_needs_review,
                rejected=batch_result.total_rejected,
                no_candidates=batch_result.total_no_candidates,
                avg_confidence=batch_result.average_confidence
            )
            return JSONResponse(status_code=200, content=resp.model_dump())
        except Exception as exc:  # noqa: BLE001
            logger.exception("a2a.reconcile.error", request_id=req.id, error=str(exc), error_type=type(exc).__name__)
            return JSONResponse(
                status_code=200,
                content=JSONRPCResponse(
                    id=req.id,
                    error=JSONRPCError(
                        code=500,
                        message="Reconciliation failed",
                        data={"detail": str(exc)},
                    ),
                ).model_dump(),
            )

    # EXECUTE (ASYNC JOB PLACEHOLDER) ----------------------------------------------
    if req.method == "execute":
        # For Stage 7 we return a placeholder; future stages may enqueue a background job.
        params = req.params or {}
        job_id = f"recon-{req.id}"
        logger.info("a2a.execute.start", request_id=req.id, job_id=job_id, params=params)
        
        # Return a Task object for async execution
        result = Task(
            id=job_id,
            status=TaskStatus(
                state="pending",
                progress=0.0,
                message="Reconciliation job accepted (async execution placeholder)"
            ),
            result={
                "job_id": job_id,
                "params": params,
                "state": "pending"
            }
        )
        resp = JSONRPCResponse(id=req.id, result=result)
        logger.info("a2a.execute.accepted", request_id=req.id, job_id=job_id)
        return JSONResponse(status_code=200, content=resp.model_dump())

    # For message/send and execute (and anything else), respond as not implemented
    logger.warning("a2a.method.not_implemented", method=req.method, request_id=req.id)
    not_impl = _method_not_implemented(req.id, req.method)
    return JSONResponse(status_code=200, content=not_impl.model_dump())
