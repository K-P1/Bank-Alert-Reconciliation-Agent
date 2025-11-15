"""Action executor with retry logic and transactional guarantees."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.config import get_actions_config
from app.actions.models import ActionResult, ActionStatus, WorkflowPolicy
from app.actions.handler import ActionHandler

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    Executes actions with retry logic and transactional guarantees.

    Handles:
    - Retry with exponential backoff
    - Transactional rollback on failure
    - Async execution
    - Error recovery
    """

    def __init__(
        self,
        session: AsyncSession,
        policy: Optional[WorkflowPolicy] = None,
    ):
        """
        Initialize action executor.

        Args:
            session: Database session
            policy: Workflow policy
        """
        self.session = session
        self.policy = policy or WorkflowPolicy()
        self.config = get_actions_config()
        self.handler = ActionHandler(session, policy)

        logger.info("ActionExecutor initialized")

    async def execute_with_retry(
        self,
        match_id: int,
        email_id: int,
        transaction_id: Optional[int],
        match_status: str,
        confidence: float,
        metadata: Optional[dict] = None,
        actor: str = "system",
    ) -> list[ActionResult]:
        """
        Execute actions with retry logic.

        Args:
            match_id: Match database ID
            email_id: Email database ID
            transaction_id: Transaction database ID
            match_status: Match status
            confidence: Match confidence
            metadata: Additional metadata
            actor: Actor triggering actions

        Returns:
            List of action results
        """
        attempt = 0
        last_error = None

        while attempt <= self.config.MAX_RETRIES:
            try:
                logger.debug(
                    f"[EXECUTOR] Executing actions (attempt {attempt + 1}/{self.config.MAX_RETRIES + 1})"
                )

                # Execute actions
                results = await self.handler.process_match_result(
                    match_id=match_id,
                    email_id=email_id,
                    transaction_id=transaction_id,
                    match_status=match_status,
                    confidence=confidence,
                    metadata=metadata,
                    actor=actor,
                )

                # Check if any critical actions failed
                critical_failures = [
                    r
                    for r in results
                    if r.status == ActionStatus.FAILED
                    and r.action_type.value in ["mark_verified", "update_status"]
                ]

                if critical_failures and attempt < self.config.MAX_RETRIES:
                    logger.warning(
                        f"[EXECUTOR] Critical action(s) failed, retrying... "
                        f"(attempt {attempt + 1})"
                    )
                    attempt += 1
                    delay = self._calculate_retry_delay(attempt)
                    await asyncio.sleep(delay)
                    continue

                # Success or non-critical failures
                logger.info(
                    f"[EXECUTOR] ✓ Actions executed successfully | "
                    f"Success: {sum(1 for r in results if r.status == ActionStatus.SUCCESS)} | "
                    f"Failed: {sum(1 for r in results if r.status == ActionStatus.FAILED)}"
                )

                return results

            except Exception as e:
                last_error = e
                logger.error(
                    f"[EXECUTOR] Action execution failed (attempt {attempt + 1}): {e}",
                    exc_info=True,
                )

                # Rollback transaction
                await self.session.rollback()

                if attempt < self.config.MAX_RETRIES:
                    attempt += 1
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(f"[EXECUTOR] Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    break

        # All retries exhausted
        logger.error(
            f"[EXECUTOR] All retries exhausted for match {match_id}, last error: {last_error}"
        )

        # Return empty results with error note
        return []

    async def execute_async(
        self,
        match_id: int,
        email_id: int,
        transaction_id: Optional[int],
        match_status: str,
        confidence: float,
        metadata: Optional[dict] = None,
        actor: str = "system",
    ) -> asyncio.Task:
        """
        Execute actions asynchronously (fire and forget).

        Returns a task that can be awaited later if needed.
        """
        if not self.config.ENABLE_ASYNC_ACTIONS:
            logger.debug("[EXECUTOR] Async actions disabled, executing synchronously")
            results = await self.execute_with_retry(
                match_id,
                email_id,
                transaction_id,
                match_status,
                confidence,
                metadata,
                actor,
            )
            # Return a completed task
            task = asyncio.create_task(asyncio.sleep(0))
            task.set_result(results)
            return task

        # Create async task
        task = asyncio.create_task(
            self.execute_with_retry(
                match_id,
                email_id,
                transaction_id,
                match_status,
                confidence,
                metadata,
                actor,
            )
        )

        logger.debug(f"[EXECUTOR] Async task created for match {match_id}")
        return task

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff."""
        delay = self.config.RETRY_DELAY_SECONDS * (
            self.config.RETRY_BACKOFF_FACTOR ** (attempt - 1)
        )
        return min(delay, self.config.RETRY_MAX_DELAY_SECONDS)


# Convenience function
async def execute_actions_for_match(
    session: AsyncSession,
    match_id: int,
    email_id: int,
    transaction_id: Optional[int],
    match_status: str,
    confidence: float,
    metadata: Optional[dict] = None,
    actor: str = "system",
    policy: Optional[WorkflowPolicy] = None,
) -> list[ActionResult]:
    """
    Convenience function to execute actions for a match.

    Args:
        session: Database session
        match_id: Match database ID
        email_id: Email database ID
        transaction_id: Transaction database ID
        match_status: Match status
        confidence: Match confidence
        metadata: Additional metadata
        actor: Actor triggering actions
        policy: Workflow policy

    Returns:
        List of action results
    """
    executor = ActionExecutor(session, policy)
    return await executor.execute_with_retry(
        match_id=match_id,
        email_id=email_id,
        transaction_id=transaction_id,
        match_status=match_status,
        confidence=confidence,
        metadata=metadata,
        actor=actor,
    )
