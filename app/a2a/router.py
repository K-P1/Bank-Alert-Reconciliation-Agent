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
    extract_hours,
    extract_interval,
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

    # Register: fetch_emails
    interpreter.register_command(
        name="fetch_emails",
        patterns=[
            r"\bfetch\s+(emails?|alerts?)\b",
            r"\bget\s+(new\s+)?(emails?|alerts?)\b",
            r"\bcheck\s+(for\s+)?(new\s+)?(emails?|alerts?)\b",
            r"\bretrieve\s+(emails?|alerts?)\b",
            r"\bpull\s+(emails?|alerts?)\b",
        ],
        handler=None,
        description="Fetch new emails from IMAP server",
        examples=[
            "fetch emails",
            "get new alerts",
            "check for new emails",
            "retrieve emails",
        ],
    )

    # Register: get_email_status
    interpreter.register_command(
        name="get_email_status",
        patterns=[
            r"\bemail\s+(fetcher\s+)?status\b",
            r"\bcheck\s+email\s+service\b",
            r"\bemail\s+fetcher\s+state\b",
            r"\bis\s+email\s+fetcher\s+running\b",
        ],
        handler=None,
        description="Get email fetcher status and metrics",
        examples=[
            "email status",
            "check email service",
            "is email fetcher running",
        ],
    )

    # Register: start_email_fetcher
    interpreter.register_command(
        name="start_email_fetcher",
        patterns=[
            r"\bstart\s+email\s+fetcher\b",
            r"\benable\s+email\s+(fetching|polling)\b",
            r"\bturn\s+on\s+email\s+service\b",
            r"\bactivate\s+email\s+fetcher\b",
        ],
        handler=None,
        description="Start the email fetcher background service",
        examples=[
            "start email fetcher",
            "enable email fetching",
            "turn on email service",
        ],
    )

    # Register: stop_email_fetcher
    interpreter.register_command(
        name="stop_email_fetcher",
        patterns=[
            r"\bstop\s+email\s+fetcher\b",
            r"\bdisable\s+email\s+(fetching|polling)\b",
            r"\bturn\s+off\s+email\s+service\b",
            r"\bdeactivate\s+email\s+fetcher\b",
        ],
        handler=None,
        description="Stop the email fetcher background service",
        examples=[
            "stop email fetcher",
            "disable email fetching",
            "turn off email service",
        ],
    )

    # Register: poll_transactions
    interpreter.register_command(
        name="poll_transactions",
        patterns=[
            r"\bpoll\s+transactions?\b",
            r"\bfetch\s+transactions?\b",
            r"\bget\s+(new\s+)?transactions?\b",
            r"\bretrieve\s+transactions?\b",
            r"\bcheck\s+(for\s+)?(new\s+)?transactions?\b",
        ],
        handler=None,
        description="Fetch new transactions from API",
        examples=[
            "poll transactions",
            "fetch transactions",
            "get new transactions",
            "check for transactions",
        ],
    )

    # Register: get_transaction_status
    interpreter.register_command(
        name="get_transaction_status",
        patterns=[
            r"\btransaction\s+(poller\s+)?status\b",
            r"\bcheck\s+transaction\s+service\b",
            r"\btransaction\s+poller\s+state\b",
            r"\bis\s+transaction\s+poller\s+running\b",
        ],
        handler=None,
        description="Get transaction poller status and metrics",
        examples=[
            "transaction status",
            "check transaction service",
            "is transaction poller running",
        ],
    )

    # Register: start_transaction_poller
    interpreter.register_command(
        name="start_transaction_poller",
        patterns=[
            r"\bstart\s+transaction\s+poller\b",
            r"\benable\s+transaction\s+(fetching|polling)\b",
            r"\bturn\s+on\s+transaction\s+service\b",
            r"\bactivate\s+transaction\s+poller\b",
        ],
        handler=None,
        description="Start the transaction poller background service",
        examples=[
            "start transaction poller",
            "enable transaction polling",
            "turn on transaction service",
        ],
    )

    # Register: stop_transaction_poller
    interpreter.register_command(
        name="stop_transaction_poller",
        patterns=[
            r"\bstop\s+transaction\s+poller\b",
            r"\bdisable\s+transaction\s+(fetching|polling)\b",
            r"\bturn\s+off\s+transaction\s+service\b",
            r"\bdeactivate\s+transaction\s+poller\b",
        ],
        handler=None,
        description="Stop the transaction poller background service",
        examples=[
            "stop transaction poller",
            "disable transaction polling",
            "turn off transaction service",
        ],
    )

    # Register: get_workflow_policy
    interpreter.register_command(
        name="get_workflow_policy",
        patterns=[
            r"\bworkflow\s+policy\b",
            r"\baction\s+policy\b",
            r"\bget\s+(workflow\s+)?configuration\b",
            r"\bshow\s+(workflow\s+)?rules\b",
            r"\bwhat\s+actions\s+are\s+configured\b",
        ],
        handler=None,
        description="Get current workflow policy configuration",
        examples=[
            "workflow policy",
            "show workflow rules",
            "get configuration",
            "what actions are configured",
        ],
    )

    # Register: get_action_audits
    interpreter.register_command(
        name="get_action_audits",
        patterns=[
            r"\baction\s+audits?\b",
            r"\bshow\s+action\s+(logs?|history)\b",
            r"\blist\s+actions?\s+(executed|performed)\b",
            r"\baction\s+execution\s+history\b",
        ],
        handler=None,
        description="Get action audit logs with execution history",
        examples=[
            "action audits",
            "show action logs",
            "list actions executed",
            "action history",
        ],
        param_extractors={"limit": extract_limit, "hours": extract_hours},
    )

    # Register: get_action_statistics
    interpreter.register_command(
        name="get_action_statistics",
        patterns=[
            r"\baction\s+statistics\b",
            r"\baction\s+stats\b",
            r"\baction\s+metrics\b",
            r"\baction\s+performance\b",
            r"\bhow\s+many\s+actions\b",
        ],
        handler=None,
        description="Get action execution statistics",
        examples=[
            "action statistics",
            "action stats",
            "action metrics",
            "how many actions executed",
        ],
        param_extractors={"hours": extract_hours},
    )

    # Register: get_automation_status
    interpreter.register_command(
        name="get_automation_status",
        patterns=[
            r"\bautomation\s+status\b",
            r"\bcheck\s+automation\b",
            r"\bis\s+automation\s+running\b",
            r"\bautomation\s+state\b",
        ],
        handler=None,
        description="Get automation service status and metrics",
        examples=[
            "automation status",
            "check automation",
            "is automation running",
        ],
    )

    # Register: start_automation
    interpreter.register_command(
        name="start_automation",
        patterns=[
            r"\bstart\s+automation\b",
            r"\benable\s+automation\b",
            r"\bturn\s+on\s+automation\b",
            r"\bactivate\s+automation\b",
            r"\bbegin\s+auto(mated)?\s+reconciliation\b",
        ],
        handler=None,
        description="Start the automation background service",
        examples=[
            "start automation",
            "enable automation",
            "turn on automation",
            "begin automated reconciliation",
        ],
        param_extractors={"interval": extract_interval},
    )

    # Register: stop_automation
    interpreter.register_command(
        name="stop_automation",
        patterns=[
            r"\bstop\s+automation\b",
            r"\bdisable\s+automation\b",
            r"\bturn\s+off\s+automation\b",
            r"\bdeactivate\s+automation\b",
            r"\bhalt\s+auto(mated)?\s+reconciliation\b",
        ],
        handler=None,
        description="Stop the automation background service",
        examples=[
            "stop automation",
            "disable automation",
            "turn off automation",
        ],
    )

    # Register: run_automation_once
    interpreter.register_command(
        name="run_automation_once",
        patterns=[
            r"\brun\s+automation\s+once\b",
            r"\bmanual\s+automation\s+(run|cycle)\b",
            r"\brun\s+(full\s+)?reconciliation\s+cycle\b",
            r"\bexecute\s+complete\s+workflow\b",
            r"\bdo\s+one\s+automation\s+cycle\b",
        ],
        handler=None,
        description="Run a single complete automation cycle manually",
        examples=[
            "run automation once",
            "run full reconciliation cycle",
            "execute complete workflow",
            "manual automation run",
        ],
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

    logger.info(
        "command_interpreter.initialized", command_count=len(interpreter.commands)
    )


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
    role: str = "agent"
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
    logger.info(
        "a2a.request.received", agent_name=agent_name, path=str(request.url.path)
    )

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
                                },
                            ),
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
                        message_parts.append(
                            MessagePart(kind="text", text=result_data["summary"])
                        )

                    # Add artifacts as data
                    if result_data.get("artifacts"):
                        message_parts.append(
                            MessagePart(kind="data", data=result_data["artifacts"])
                        )

                    # Add metadata
                    metadata = {
                        **result_data.get("meta", {}),
                        "interpreted_from": user_text,
                        "command": command_match.command_name,
                        "confidence": command_match.confidence,
                        "status": result_data.get("status", "success"),
                    }

                    result = Message(parts=message_parts, metadata=metadata)
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

        status_text = "🟢 **BARA Service is healthy**\n\n"
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
                    },
                ),
            ]
        )
        resp = JSONRPCResponse(id=req.id, result=result)
        logger.info(
            "a2a.status.success", request_id=req.id, agent=agent_name, env=settings.ENV
        )
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
            summarize=summarize,
        )

        try:
            batch_result: BatchMatchResult

            if email_ids:
                # Explicit set of emails provided
                logger.info(
                    "a2a.reconcile.mode.targeted",
                    email_ids=email_ids,
                    count=len(email_ids),
                )
                engine = MatchingEngine(db)
                match_repo = MatchRepository(Match, db)
                results: List[MatchResult] = []
                for eid in email_ids:
                    logger.debug(
                        "a2a.reconcile.processing_email", email_id=eid, rematch=rematch
                    )
                    if rematch:
                        res = await engine.rematch_email(eid)
                        logger.info(
                            "a2a.reconcile.email_rematched",
                            email_id=eid,
                            status=res.match_status,
                        )
                    else:
                        # Fetch email and match only if no existing match
                        repo = EmailRepository(Email, db)
                        email_model = await repo.get_by_id(eid)
                        if not email_model:
                            # Skip non-existent email IDs
                            logger.warning(
                                "a2a.reconcile.email_not_found",
                                email_id=eid,
                                request_id=req.id,
                            )
                            continue
                        # Check if match already exists using repository
                        if await match_repo.exists_for_email(eid):
                            logger.debug(
                                "a2a.reconcile.email_already_matched", email_id=eid
                            )
                            continue
                        res = await engine.rematch_email(eid)
                        logger.info(
                            "a2a.reconcile.email_matched",
                            email_id=eid,
                            status=res.match_status,
                        )
                    results.append(res)
                # Build synthetic batch result
                from app.matching.models import BatchMatchResult as BMR

                batch_result = BMR()
                for r in results:
                    batch_result.add_result(r)
                batch_result.finalize()
                logger.info(
                    "a2a.reconcile.targeted_complete", emails_processed=len(results)
                )
            else:
                # Match all currently unmatched (respect limit)
                logger.info("a2a.reconcile.mode.unmatched", limit=limit)
                batch_result = await match_unmatched(db, limit=limit)
                logger.info(
                    "a2a.reconcile.unmatched_complete",
                    emails_processed=batch_result.total_emails,
                )

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

            result = Message(parts=message_parts, metadata=metadata)
            resp = JSONRPCResponse(id=req.id, result=result)
            logger.info(
                "a2a.reconcile.success",
                request_id=req.id,
                emails=batch_result.total_emails,
                matched=batch_result.total_matched,
                needs_review=batch_result.total_needs_review,
                rejected=batch_result.total_rejected,
                no_candidates=batch_result.total_no_candidates,
                avg_confidence=batch_result.average_confidence,
            )
            return JSONResponse(status_code=200, content=resp.model_dump())
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "a2a.reconcile.error",
                request_id=req.id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
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
        # Enhanced execute method with automation control support
        params = req.params or {}
        action = params.get("action", "start_automation")

        logger.info(
            "a2a.execute.start", request_id=req.id, action=action, params=params
        )

        # Import automation
        from app.actions.automation import get_automation

        automation = get_automation()

        try:
            # Handle automation control commands
            if action == "start_automation":
                # Start background automation
                interval = params.get("interval_seconds", 900)  # Default 15 min
                enable_actions = params.get("enable_actions", True)

                if automation._running:
                    message_text = "⚠️ **Automation already running**\n\n"
                    message_text += (
                        f"**Current interval:** {automation.interval_seconds}s\n"
                    )
                    message_text += (
                        f"**Actions enabled:** {automation.enable_actions}\n"
                    )
                    message_text += f"**Total runs:** {automation.total_runs}\n"

                    result = Message(
                        parts=[
                            MessagePart(kind="text", text=message_text),
                            MessagePart(kind="data", data=automation.get_status()),
                        ]
                    )
                    resp = JSONRPCResponse(id=req.id, result=result)
                    return JSONResponse(status_code=200, content=resp.model_dump())

                # Update configuration if provided
                if interval:
                    automation.interval_seconds = interval
                automation.enable_actions = enable_actions

                await automation.start()

                message_text = "✅ **Automation started successfully!**\n\n"
                message_text += f"**Interval:** Every {automation.interval_seconds}s ({automation.interval_seconds // 60} minutes)\n"
                message_text += f"**Actions:** {'Enabled' if automation.enable_actions else 'Disabled'}\n\n"
                message_text += "The system will now automatically:\n"
                message_text += "  1. Fetch new emails\n"
                message_text += "  2. Poll new transactions\n"
                message_text += "  3. Match unprocessed emails\n"
                message_text += "  4. Execute post-processing actions\n"

                result = Message(
                    parts=[
                        MessagePart(kind="text", text=message_text),
                        MessagePart(kind="data", data=automation.get_status()),
                    ]
                )
                resp = JSONRPCResponse(id=req.id, result=result)
                logger.info("a2a.execute.automation_started", request_id=req.id)
                return JSONResponse(status_code=200, content=resp.model_dump())

            elif action == "stop_automation":
                # Stop background automation
                if not automation._running:
                    message_text = "⚠️ **Automation not running**\n\n"
                    message_text += (
                        "Use `start_automation` to begin automatic reconciliation.\n"
                    )

                    result = Message(
                        parts=[
                            MessagePart(kind="text", text=message_text),
                            MessagePart(kind="data", data=automation.get_status()),
                        ]
                    )
                    resp = JSONRPCResponse(id=req.id, result=result)
                    return JSONResponse(status_code=200, content=resp.model_dump())

                await automation.stop()

                message_text = "🛑 **Automation stopped**\n\n"
                message_text += f"**Total runs completed:** {automation.total_runs}\n"
                message_text += f"**Successful:** {automation.successful_runs}\n"
                message_text += f"**Failed:** {automation.failed_runs}\n"

                result = Message(
                    parts=[
                        MessagePart(kind="text", text=message_text),
                        MessagePart(kind="data", data=automation.get_status()),
                    ]
                )
                resp = JSONRPCResponse(id=req.id, result=result)
                logger.info("a2a.execute.automation_stopped", request_id=req.id)
                return JSONResponse(status_code=200, content=resp.model_dump())

            elif action == "automation_status":
                # Get automation status
                status = automation.get_status()

                if status["running"]:
                    message_text = "✅ **Automation is RUNNING**\n\n"
                    message_text += f"**Interval:** {status['interval_seconds']}s ({status['interval_seconds'] // 60} min)\n"
                    message_text += f"**Actions:** {'Enabled' if status['actions_enabled'] else 'Disabled'}\n\n"
                    message_text += "**Statistics:**\n"
                    message_text += (
                        f"  • Total runs: {status['metrics']['total_runs']}\n"
                    )
                    message_text += (
                        f"  • Successful: {status['metrics']['successful_runs']}\n"
                    )
                    message_text += f"  • Failed: {status['metrics']['failed_runs']}\n"
                    if status["metrics"]["last_run_at"]:
                        message_text += (
                            f"  • Last run: {status['metrics']['last_run_at']}\n"
                        )
                        if status["metrics"]["last_run_stats"]:
                            stats = status["metrics"]["last_run_stats"]
                            message_text += f"  • Last run: {stats.get('emails_matched', 0)} emails, {stats.get('actions_executed', 0)} actions\n"
                else:
                    message_text = "⚪ **Automation is STOPPED**\n\n"
                    message_text += (
                        f"**Total runs:** {status['metrics']['total_runs']}\n"
                    )
                    message_text += (
                        f"**Successful:** {status['metrics']['successful_runs']}\n"
                    )
                    message_text += (
                        f"**Failed:** {status['metrics']['failed_runs']}\n\n"
                    )
                    message_text += (
                        "Use `start_automation` to begin automatic reconciliation.\n"
                    )

                result = Message(
                    parts=[
                        MessagePart(kind="text", text=message_text),
                        MessagePart(kind="data", data=status),
                    ]
                )
                resp = JSONRPCResponse(id=req.id, result=result)
                logger.info(
                    "a2a.execute.automation_status",
                    request_id=req.id,
                    running=status["running"],
                )
                return JSONResponse(status_code=200, content=resp.model_dump())

            elif action == "run_once":
                # Manually trigger one reconciliation cycle
                message_text = "🔄 **Starting manual reconciliation cycle...**\n\n"

                result = Message(parts=[MessagePart(kind="text", text=message_text)])
                resp = JSONRPCResponse(id=req.id, result=result)

                # Execute cycle
                stats = await automation.run_once()

                success = len(stats.get("errors", [])) == 0

                if success:
                    summary_text = "✅ **Manual reconciliation complete!**\n\n"
                else:
                    summary_text = "⚠️ **Reconciliation completed with errors**\n\n"

                summary_text += "**Results:**\n"
                summary_text += (
                    f"  • Emails fetched: {stats.get('emails_fetched', 0)}\n"
                )
                summary_text += (
                    f"  • Transactions polled: {stats.get('transactions_polled', 0)}\n"
                )
                summary_text += (
                    f"  • Emails matched: {stats.get('emails_matched', 0)}\n"
                )
                summary_text += (
                    f"  • Matches successful: {stats.get('matches_successful', 0)}\n"
                )
                summary_text += (
                    f"  • Needs review: {stats.get('matches_needs_review', 0)}\n"
                )
                summary_text += (
                    f"  • Actions executed: {stats.get('actions_executed', 0)}\n"
                )

                if stats.get("errors"):
                    summary_text += f"\n**Errors:** {len(stats['errors'])}\n"
                    for error in stats["errors"][:3]:  # Show first 3 errors
                        summary_text += f"  • {error}\n"

                result = Message(
                    parts=[
                        MessagePart(kind="text", text=summary_text),
                        MessagePart(kind="data", data=stats),
                    ]
                )
                resp = JSONRPCResponse(id=req.id, result=result)
                logger.info(
                    "a2a.execute.run_once_complete", request_id=req.id, success=success
                )
                return JSONResponse(status_code=200, content=resp.model_dump())

            else:
                # Unknown action - return error
                logger.warning(
                    "a2a.execute.unknown_action", action=action, request_id=req.id
                )
                return JSONResponse(
                    status_code=200,
                    content=JSONRPCResponse(
                        id=req.id,
                        error=JSONRPCError(
                            code=-32602,
                            message=f"Unknown action: {action}",
                            data={
                                "valid_actions": [
                                    "start_automation",
                                    "stop_automation",
                                    "automation_status",
                                    "run_once",
                                ]
                            },
                        ),
                    ).model_dump(),
                )

        except Exception as exc:
            logger.exception(
                "a2a.execute.error",
                request_id=req.id,
                action=action,
                error=str(exc),
            )
            return JSONResponse(
                status_code=200,
                content=JSONRPCResponse(
                    id=req.id,
                    error=JSONRPCError(
                        code=500,
                        message=f"Execute action failed: {action}",
                        data={"detail": str(exc)},
                    ),
                ).model_dump(),
            )

    # For message/send and execute (and anything else), respond as not implemented
    logger.warning("a2a.method.not_implemented", method=req.method, request_id=req.id)
    not_impl = _method_not_implemented(req.id, req.method)
    return JSONResponse(status_code=200, content=not_impl.model_dump())
