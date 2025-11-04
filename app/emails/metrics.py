"""Metrics tracking for email fetcher and parser."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class FetchRunMetrics:
    """Metrics for a single fetch run."""

    run_id: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    status: Literal["SUCCESS", "PARTIAL", "FAILED"]

    # Fetching metrics
    emails_fetched: int
    emails_filtered: int
    emails_classified: int
    emails_parsed: int
    emails_stored: int
    emails_failed: int

    # Classification metrics (if LLM enabled)
    classified_as_alert: int
    classified_as_non_alert: int

    # Parsing metrics
    parsed_with_llm: int
    parsed_with_regex: int
    parsed_hybrid: int

    # Confidence metrics
    avg_confidence: float
    min_confidence: float
    max_confidence: float
    low_confidence_count: int  # Below threshold

    # Field extraction metrics
    amount_extracted_count: int
    currency_extracted_count: int
    reference_extracted_count: int
    timestamp_extracted_count: int

    # Error tracking
    error_message: str | None = None
    errors: list[str] | None = None


class ParserMetrics:
    """Metrics tracker for email fetcher and parser."""

    def __init__(self, max_history: int = 100):
        """Initialize metrics tracker.

        Args:
            max_history: Maximum number of runs to keep in history
        """
        self.max_history = max_history
        self.runs: deque[FetchRunMetrics] = deque(maxlen=max_history)

        # Current run metrics (being collected)
        self._current_run: dict | None = None

    def start_run(self, run_id: str) -> None:
        """Start tracking a new fetch run.

        Args:
            run_id: Unique run identifier
        """
        self._current_run = {
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc),
            "emails_fetched": 0,
            "emails_filtered": 0,
            "emails_classified": 0,
            "emails_parsed": 0,
            "emails_stored": 0,
            "emails_failed": 0,
            "classified_as_alert": 0,
            "classified_as_non_alert": 0,
            "parsed_with_llm": 0,
            "parsed_with_regex": 0,
            "parsed_hybrid": 0,
            "confidences": [],
            "amount_extracted_count": 0,
            "currency_extracted_count": 0,
            "reference_extracted_count": 0,
            "timestamp_extracted_count": 0,
            "errors": [],
        }
        logger.debug(f"Started metrics tracking for run: {run_id}")

    def record_fetch(self, count: int) -> None:
        """Record emails fetched."""
        if self._current_run:
            self._current_run["emails_fetched"] = count

    def record_filtered(self) -> None:
        """Record email filtered out."""
        if self._current_run:
            self._current_run["emails_filtered"] += 1

    def record_classified(self, is_alert: bool) -> None:
        """Record email classified."""
        if self._current_run:
            self._current_run["emails_classified"] += 1
            if is_alert:
                self._current_run["classified_as_alert"] += 1
            else:
                self._current_run["classified_as_non_alert"] += 1

    def record_parsed(self, parsing_method: str, confidence: float, fields: dict) -> None:
        """Record email parsed.

        Args:
            parsing_method: Method used (llm, regex, hybrid)
            confidence: Confidence score
            fields: Extracted fields dict
        """
        if self._current_run:
            self._current_run["emails_parsed"] += 1
            self._current_run["confidences"].append(confidence)

            # Track parsing method
            if parsing_method == "llm":
                self._current_run["parsed_with_llm"] += 1
            elif parsing_method == "regex":
                self._current_run["parsed_with_regex"] += 1
            elif parsing_method == "hybrid":
                self._current_run["parsed_hybrid"] += 1

            # Track field extraction
            if fields.get("amount") is not None:
                self._current_run["amount_extracted_count"] += 1
            if fields.get("currency") is not None:
                self._current_run["currency_extracted_count"] += 1
            if fields.get("reference") is not None:
                self._current_run["reference_extracted_count"] += 1
            if fields.get("email_timestamp") is not None:
                self._current_run["timestamp_extracted_count"] += 1

    def record_stored(self) -> None:
        """Record email stored to database."""
        if self._current_run:
            self._current_run["emails_stored"] += 1

    def record_failed(self, error: str) -> None:
        """Record email processing failure.

        Args:
            error: Error message
        """
        if self._current_run:
            self._current_run["emails_failed"] += 1
            self._current_run["errors"].append(error)

    def end_run(self, status: Literal["SUCCESS", "PARTIAL", "FAILED"], error_message: str | None = None) -> None:
        """End current run and save metrics.

        Args:
            status: Run status
            error_message: Error message if failed
        """
        if not self._current_run:
            return

        ended_at = datetime.now(timezone.utc)
        duration = (ended_at - self._current_run["started_at"]).total_seconds()

        # Calculate confidence statistics
        confidences = self._current_run["confidences"]
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            min_confidence = min(confidences)
            max_confidence = max(confidences)
            low_confidence_count = sum(1 for c in confidences if c < 0.7)
        else:
            avg_confidence = 0.0
            min_confidence = 0.0
            max_confidence = 0.0
            low_confidence_count = 0

        # Create metrics record
        metrics = FetchRunMetrics(
            run_id=self._current_run["run_id"],
            started_at=self._current_run["started_at"],
            ended_at=ended_at,
            duration_seconds=duration,
            status=status,
            emails_fetched=self._current_run["emails_fetched"],
            emails_filtered=self._current_run["emails_filtered"],
            emails_classified=self._current_run["emails_classified"],
            emails_parsed=self._current_run["emails_parsed"],
            emails_stored=self._current_run["emails_stored"],
            emails_failed=self._current_run["emails_failed"],
            classified_as_alert=self._current_run["classified_as_alert"],
            classified_as_non_alert=self._current_run["classified_as_non_alert"],
            parsed_with_llm=self._current_run["parsed_with_llm"],
            parsed_with_regex=self._current_run["parsed_with_regex"],
            parsed_hybrid=self._current_run["parsed_hybrid"],
            avg_confidence=avg_confidence,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            low_confidence_count=low_confidence_count,
            amount_extracted_count=self._current_run["amount_extracted_count"],
            currency_extracted_count=self._current_run["currency_extracted_count"],
            reference_extracted_count=self._current_run["reference_extracted_count"],
            timestamp_extracted_count=self._current_run["timestamp_extracted_count"],
            error_message=error_message,
            errors=self._current_run["errors"] if self._current_run["errors"] else None,
        )

        # Add to history
        self.runs.append(metrics)

        logger.info(
            f"Run {metrics.run_id} completed: "
            f"status={status}, "
            f"fetched={metrics.emails_fetched}, "
            f"parsed={metrics.emails_parsed}, "
            f"stored={metrics.emails_stored}, "
            f"duration={duration:.2f}s"
        )

        # Clear current run
        self._current_run = None

    def get_aggregate_metrics(self) -> dict:
        """Get aggregate metrics across all runs.

        Returns:
            Dict of aggregate metrics
        """
        if not self.runs:
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "success_rate": 0.0,
            }

        total_runs = len(self.runs)
        successful_runs = sum(1 for r in self.runs if r.status == "SUCCESS")
        partial_runs = sum(1 for r in self.runs if r.status == "PARTIAL")
        failed_runs = sum(1 for r in self.runs if r.status == "FAILED")

        total_fetched = sum(r.emails_fetched for r in self.runs)
        total_parsed = sum(r.emails_parsed for r in self.runs)
        total_stored = sum(r.emails_stored for r in self.runs)
        total_filtered = sum(r.emails_filtered for r in self.runs)

        avg_duration = sum(r.duration_seconds for r in self.runs) / total_runs
        avg_emails_per_run = total_fetched / total_runs if total_runs > 0 else 0

        # Parsing method distribution
        total_llm = sum(r.parsed_with_llm for r in self.runs)
        total_regex = sum(r.parsed_with_regex for r in self.runs)
        total_hybrid = sum(r.parsed_hybrid for r in self.runs)

        # Confidence distribution
        all_confidences = []
        for run in self.runs:
            if run.avg_confidence > 0:
                all_confidences.append(run.avg_confidence)

        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

        # Field extraction rates
        total_emails_parsed = total_parsed if total_parsed > 0 else 1
        amount_extraction_rate = sum(r.amount_extracted_count for r in self.runs) / total_emails_parsed
        currency_extraction_rate = sum(r.currency_extracted_count for r in self.runs) / total_emails_parsed
        reference_extraction_rate = sum(r.reference_extracted_count for r in self.runs) / total_emails_parsed
        timestamp_extraction_rate = sum(r.timestamp_extracted_count for r in self.runs) / total_emails_parsed

        return {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "partial_runs": partial_runs,
            "failed_runs": failed_runs,
            "success_rate": (successful_runs / total_runs * 100) if total_runs > 0 else 0.0,
            "total_emails_fetched": total_fetched,
            "total_emails_parsed": total_parsed,
            "total_emails_stored": total_stored,
            "total_emails_filtered": total_filtered,
            "average_duration_seconds": avg_duration,
            "average_emails_per_run": avg_emails_per_run,
            "parsing_methods": {
                "llm": total_llm,
                "regex": total_regex,
                "hybrid": total_hybrid,
            },
            "average_confidence": avg_confidence,
            "field_extraction_rates": {
                "amount": amount_extraction_rate,
                "currency": currency_extraction_rate,
                "reference": reference_extraction_rate,
                "timestamp": timestamp_extraction_rate,
            },
        }

    def get_last_run(self) -> FetchRunMetrics | None:
        """Get metrics from last run."""
        return self.runs[-1] if self.runs else None

    def get_recent_runs(self, count: int = 10) -> list[FetchRunMetrics]:
        """Get metrics from recent runs.

        Args:
            count: Number of recent runs to return

        Returns:
            List of recent run metrics
        """
        return list(self.runs)[-count:] if self.runs else []
