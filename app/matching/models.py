"""Data models for matching results and candidates."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class RuleScore(BaseModel):
    """Score from a single matching rule."""

    rule_name: str = Field(..., description="Name of the rule")
    score: float = Field(..., ge=0.0, le=1.0, description="Rule score (0-1)")
    weight: float = Field(..., ge=0.0, le=1.0, description="Rule weight in total score")
    weighted_score: float = Field(..., ge=0.0, le=1.0, description="Score × weight")
    details: dict = Field(
        default_factory=dict, description="Additional rule-specific details"
    )


class MatchCandidate(BaseModel):
    """A candidate transaction that might match an email."""

    # Transaction identification
    transaction_id: int = Field(..., description="Database ID of transaction")
    external_transaction_id: str = Field(..., description="External transaction ID")

    # Transaction details
    amount: Decimal = Field(..., description="Transaction amount")
    currency: str = Field(..., description="Currency code")
    timestamp: datetime = Field(..., description="Transaction timestamp")
    reference: str | None = Field(default=None, description="Transaction reference")
    account_ref: str | None = Field(default=None, description="Account reference")
    description: str | None = Field(default=None, description="Transaction description")

    # Matching scores
    rule_scores: list[RuleScore] = Field(
        default_factory=list, description="Individual rule scores"
    )
    total_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Total confidence score"
    )

    # Ranking
    rank: int | None = Field(default=None, description="Rank among candidates (1=best)")

    # Additional metadata
    matched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When matching was performed",
    )

    def add_rule_score(
        self, rule_name: str, score: float, weight: float, details: dict | None = None
    ) -> None:
        """Add a rule score and update total."""
        weighted = score * weight
        rule_score = RuleScore(
            rule_name=rule_name,
            score=score,
            weight=weight,
            weighted_score=weighted,
            details=details or {},
        )
        self.rule_scores.append(rule_score)
        self.total_score += weighted

    def get_score_breakdown(self) -> dict:
        """Get detailed score breakdown."""
        return {
            "total_score": self.total_score,
            "rules": [
                {
                    "rule": rs.rule_name,
                    "score": rs.score,
                    "weight": rs.weight,
                    "weighted_score": rs.weighted_score,
                    "details": rs.details,
                }
                for rs in self.rule_scores
            ],
        }


class MatchResult(BaseModel):
    """Result of matching an email to transactions."""

    # Email identification
    email_id: int = Field(..., description="Database ID of email")
    email_message_id: str = Field(..., description="Email message ID")

    # Match status
    matched: bool = Field(default=False, description="Whether a match was found")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall match confidence"
    )
    match_status: Literal[
        "auto_matched", "needs_review", "rejected", "no_candidates"
    ] = Field(..., description="Match decision status")

    # Best match (if any)
    best_candidate: MatchCandidate | None = Field(
        default=None, description="Best matching candidate"
    )

    # Alternative matches
    alternative_candidates: list[MatchCandidate] = Field(
        default_factory=list, description="Other potential matches"
    )

    # Matching metadata
    total_candidates_retrieved: int = Field(
        default=0, description="Total candidates retrieved"
    )
    total_candidates_scored: int = Field(
        default=0, description="Total candidates scored"
    )
    matching_method: str = Field(default="hybrid", description="Matching method used")

    # Timestamps
    matched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When matching was performed",
    )

    # Processing notes
    notes: list[str] = Field(
        default_factory=list, description="Processing notes and warnings"
    )

    def add_note(self, note: str) -> None:
        """Add a processing note."""
        self.notes.append(note)

    def set_best_match(self, candidate: MatchCandidate) -> None:
        """Set the best match and update status."""
        self.best_candidate = candidate
        self.matched = True
        self.confidence = candidate.total_score

    def get_match_summary(self) -> dict:
        """Get a summary of the match result."""
        return {
            "email_id": self.email_id,
            "matched": self.matched,
            "confidence": self.confidence,
            "status": self.match_status,
            "transaction_id": (
                self.best_candidate.transaction_id if self.best_candidate else None
            ),
            "external_transaction_id": (
                self.best_candidate.external_transaction_id
                if self.best_candidate
                else None
            ),
            "candidates_retrieved": self.total_candidates_retrieved,
            "alternatives_count": len(self.alternative_candidates),
            "matched_at": self.matched_at.isoformat(),
        }


class BatchMatchResult(BaseModel):
    """Result of matching multiple emails."""

    results: list[MatchResult] = Field(
        default_factory=list, description="Individual match results"
    )

    # Aggregate statistics
    total_emails: int = Field(default=0, description="Total emails processed")
    total_matched: int = Field(default=0, description="Total successfully matched")
    total_needs_review: int = Field(default=0, description="Total needing review")
    total_rejected: int = Field(default=0, description="Total rejected")
    total_no_candidates: int = Field(default=0, description="Total with no candidates")

    # Performance metrics
    average_confidence: float = Field(
        default=0.0, description="Average confidence of matches"
    )
    average_candidates_per_email: float = Field(
        default=0.0, description="Average candidates retrieved"
    )

    # Timestamps
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When batch started",
    )
    completed_at: datetime | None = Field(
        default=None, description="When batch completed"
    )

    def add_result(self, result: MatchResult) -> None:
        """Add a match result and update statistics."""
        self.results.append(result)
        self.total_emails += 1

        if result.matched:
            self.total_matched += 1

        if result.match_status == "needs_review":
            self.total_needs_review += 1
        elif result.match_status == "rejected":
            self.total_rejected += 1
        elif result.match_status == "no_candidates":
            self.total_no_candidates += 1

    def finalize(self) -> None:
        """Calculate final statistics."""
        self.completed_at = datetime.now(timezone.utc)

        if self.total_emails > 0:
            matched_confidences = [r.confidence for r in self.results if r.matched]
            self.average_confidence = (
                sum(matched_confidences) / len(matched_confidences)
                if matched_confidences
                else 0.0
            )

            total_candidates = sum(r.total_candidates_retrieved for r in self.results)
            self.average_candidates_per_email = total_candidates / self.total_emails

    def get_summary(self) -> dict:
        """Get batch summary."""
        return {
            "total_emails": self.total_emails,
            "matched": self.total_matched,
            "needs_review": self.total_needs_review,
            "rejected": self.total_rejected,
            "no_candidates": self.total_no_candidates,
            "match_rate": (
                self.total_matched / self.total_emails if self.total_emails > 0 else 0.0
            ),
            "average_confidence": self.average_confidence,
            "average_candidates": self.average_candidates_per_email,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at
                else None
            ),
        }
