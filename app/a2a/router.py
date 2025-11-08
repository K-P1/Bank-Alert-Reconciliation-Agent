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
    meta: Optional[Dict[str, Any]] = None


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

    # STATUS METHOD -----------------------------------------------------------------
    if req.method == "status":
        logger.info("a2a.status.start", request_id=req.id, agent=agent_name)
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
                    f"Reconciled {batch_result.total_emails} emails | "
                    f"matched={batch_result.total_matched} review={batch_result.total_needs_review} "
                    f"rejected={batch_result.total_rejected} none={batch_result.total_no_candidates} "
                    f"avg_conf={batch_result.average_confidence:.2f}"
                )

            result = JSONRPCResult(
                status="success",
                summary=summary_text,
                artifacts=result_artifacts,
                meta={
                    "batch": batch_result.get_summary(),
                    "params": {"limit": limit, "email_ids": email_ids, "rematch": rematch},
                },
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
        result = JSONRPCResult(
            status="accepted",
            summary="Reconciliation job accepted (async execution placeholder)",
            artifacts=[{"kind": "job", "data": {"job_id": job_id, "params": params}}],
            meta={"state": "pending"},
        )
        resp = JSONRPCResponse(id=req.id, result=result)
        logger.info("a2a.execute.accepted", request_id=req.id, job_id=job_id)
        return JSONResponse(status_code=200, content=resp.model_dump())

    # For message/send and execute (and anything else), respond as not implemented
    logger.warning("a2a.method.not_implemented", method=req.method, request_id=req.id)
    not_impl = _method_not_implemented(req.id, req.method)
    return JSONResponse(status_code=200, content=not_impl.model_dump())
