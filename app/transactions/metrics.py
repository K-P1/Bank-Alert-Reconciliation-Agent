"""
Transaction poller metrics and monitoring.

Tracks polling performance, success rates, latency, and provides
observability into the poller's operations.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum


class PollStatus(str, Enum):
    """Status of a polling run."""

    SUCCESS = "success"
    PARTIAL = "partial"  # Some transactions fetched, but errors occurred
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PollRunMetrics:
    """Metrics for a single polling run."""

    run_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: PollStatus = PollStatus.SUCCESS

    # Transaction counts
    transactions_fetched: int = 0
    transactions_new: int = 0
    transactions_duplicate: int = 0
    transactions_stored: int = 0
    transactions_failed: int = 0

    # Performance metrics
    duration_seconds: float = 0.0
    api_calls: int = 0
    api_latency_seconds: float = 0.0
    db_latency_seconds: float = 0.0

    # Error tracking
    errors: List[str] = field(default_factory=list)
    error_count: int = 0

    # Additional metadata
    source: str = "unknown"
    lookback_hours: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PollRunMetrics":
        """Create from dictionary."""
        data = data.copy()
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data.get("ended_at"):
            data["ended_at"] = datetime.fromisoformat(data["ended_at"])
        data["status"] = PollStatus(data["status"])
        return cls(**data)


@dataclass
class AggregateMetrics:
    """Aggregated metrics across multiple poll runs."""

    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    partial_runs: int = 0
    skipped_runs: int = 0

    total_transactions: int = 0
    total_new_transactions: int = 0
    total_duplicates: int = 0
    total_errors: int = 0

    avg_duration_seconds: float = 0.0
    avg_api_latency_seconds: float = 0.0
    avg_transactions_per_run: float = 0.0

    first_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        for key in ["first_run", "last_run", "last_success", "last_failure"]:
            if data[key]:
                data[key] = data[key].isoformat()
        return data


class PollerMetrics:
    """
    In-memory metrics tracker for transaction poller.

    Tracks current run metrics and maintains recent history.
    For persistent metrics, use the logs table in the database.
    """

    def __init__(self, history_size: int = 100):
        """
        Initialize metrics tracker.

        Args:
            history_size: Number of recent runs to keep in memory
        """
        self.history_size = history_size
        self._current_run: Optional[PollRunMetrics] = None
        self._history: List[PollRunMetrics] = []
        self._run_counter = 0

    def start_run(self, source: str, lookback_hours: int) -> str:
        """
        Start tracking a new polling run.

        Args:
            source: Transaction source identifier
            lookback_hours: Hours to look back for transactions

        Returns:
            Run ID for this polling attempt
        """
        self._run_counter += 1
        run_id = f"poll-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{self._run_counter}"

        self._current_run = PollRunMetrics(
            run_id=run_id,
            started_at=datetime.now(timezone.utc),
            source=source,
            lookback_hours=lookback_hours,
        )

        return run_id

    def end_run(self, status: PollStatus = PollStatus.SUCCESS):
        """
        End the current polling run.

        Args:
            status: Final status of the run
        """
        if not self._current_run:
            return

        self._current_run.ended_at = datetime.now(timezone.utc)
        self._current_run.status = status
        self._current_run.duration_seconds = (
            self._current_run.ended_at - self._current_run.started_at
        ).total_seconds()

        # Add to history
        self._history.append(self._current_run)

        # Trim history to size limit
        if len(self._history) > self.history_size:
            self._history = self._history[-self.history_size :]

        self._current_run = None

    def record_api_call(self, latency_seconds: float):
        """Record an API call."""
        if self._current_run:
            self._current_run.api_calls += 1
            self._current_run.api_latency_seconds += latency_seconds

    def record_transactions(
        self, fetched: int, new: int, duplicate: int, stored: int, failed: int = 0
    ):
        """Record transaction counts."""
        if self._current_run:
            self._current_run.transactions_fetched += fetched
            self._current_run.transactions_new += new
            self._current_run.transactions_duplicate += duplicate
            self._current_run.transactions_stored += stored
            self._current_run.transactions_failed += failed

    def record_error(self, error: str):
        """Record an error during polling."""
        if self._current_run:
            self._current_run.errors.append(error)
            self._current_run.error_count += 1

    def record_db_latency(self, latency_seconds: float):
        """Record database operation latency."""
        if self._current_run:
            self._current_run.db_latency_seconds += latency_seconds

    def get_current_run(self) -> Optional[PollRunMetrics]:
        """Get metrics for the current run."""
        return self._current_run

    def get_last_run(self) -> Optional[PollRunMetrics]:
        """Get metrics for the most recent completed run."""
        return self._history[-1] if self._history else None

    def get_history(self, limit: Optional[int] = None) -> List[PollRunMetrics]:
        """
        Get recent run history.

        Args:
            limit: Maximum number of runs to return (defaults to all)

        Returns:
            List of poll run metrics, newest first
        """
        history = list(reversed(self._history))
        if limit:
            history = history[:limit]
        return history

    def get_aggregate_metrics(self, hours: Optional[int] = None) -> AggregateMetrics:
        """
        Get aggregated metrics across recent runs.

        Args:
            hours: Only include runs from the last N hours (None = all history)

        Returns:
            Aggregated metrics
        """
        runs = self._history

        if hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            runs = [r for r in runs if r.started_at >= cutoff]

        if not runs:
            return AggregateMetrics()

        metrics = AggregateMetrics()
        metrics.total_runs = len(runs)

        # Count by status
        for run in runs:
            if run.status == PollStatus.SUCCESS:
                metrics.successful_runs += 1
            elif run.status == PollStatus.FAILED:
                metrics.failed_runs += 1
            elif run.status == PollStatus.PARTIAL:
                metrics.partial_runs += 1
            elif run.status == PollStatus.SKIPPED:
                metrics.skipped_runs += 1

        # Transaction totals
        metrics.total_transactions = sum(r.transactions_fetched for r in runs)
        metrics.total_new_transactions = sum(r.transactions_new for r in runs)
        metrics.total_duplicates = sum(r.transactions_duplicate for r in runs)
        metrics.total_errors = sum(r.error_count for r in runs)

        # Averages
        if metrics.total_runs > 0:
            metrics.avg_duration_seconds = (
                sum(r.duration_seconds for r in runs) / metrics.total_runs
            )
            metrics.avg_api_latency_seconds = (
                sum(r.api_latency_seconds for r in runs) / metrics.total_runs
            )
            metrics.avg_transactions_per_run = (
                metrics.total_transactions / metrics.total_runs
            )

        # Timestamps
        metrics.first_run = runs[0].started_at
        metrics.last_run = runs[-1].started_at

        # Last success/failure
        for run in reversed(runs):
            if run.status == PollStatus.SUCCESS and not metrics.last_success:
                metrics.last_success = run.started_at
            if run.status == PollStatus.FAILED and not metrics.last_failure:
                metrics.last_failure = run.started_at
            if metrics.last_success and metrics.last_failure:
                break

        return metrics

    def get_success_rate(self, hours: Optional[int] = None) -> float:
        """
        Calculate success rate as percentage.

        Args:
            hours: Only include runs from the last N hours

        Returns:
            Success rate as float (0.0 to 1.0)
        """
        agg = self.get_aggregate_metrics(hours)
        if agg.total_runs == 0:
            return 0.0
        return agg.successful_runs / agg.total_runs

    def clear_history(self):
        """Clear all metrics history."""
        self._history.clear()
        self._current_run = None
