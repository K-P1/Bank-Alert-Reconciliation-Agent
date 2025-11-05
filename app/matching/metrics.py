"""Metrics tracking for the matching engine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.matching.models import MatchResult, BatchMatchResult

logger = logging.getLogger(__name__)


class RuleContribution(BaseModel):
    """Tracks contribution of a single rule to matching."""

    rule_name: str
    total_invocations: int = 0
    total_score: float = 0.0
    max_score: float = 0.0
    min_score: float = 1.0
    avg_score: float = 0.0
    high_scores: int = 0  # Count of scores >= 0.8

    def update(self, score: float) -> None:
        """Update rule statistics with a new score."""
        self.total_invocations += 1
        self.total_score += score
        self.max_score = max(self.max_score, score)
        self.min_score = min(self.min_score, score)
        self.avg_score = self.total_score / self.total_invocations

        if score >= 0.8:
            self.high_scores += 1


class ConfidenceDistribution(BaseModel):
    """Distribution of confidence scores."""

    very_high: int = Field(default=0, description="Confidence >= 0.90")
    high: int = Field(default=0, description="0.80 <= confidence < 0.90")
    medium: int = Field(default=0, description="0.60 <= confidence < 0.80")
    low: int = Field(default=0, description="0.40 <= confidence < 0.60")
    very_low: int = Field(default=0, description="Confidence < 0.40")

    def add_score(self, score: float) -> None:
        """Add a score to the distribution."""
        if score >= 0.90:
            self.very_high += 1
        elif score >= 0.80:
            self.high += 1
        elif score >= 0.60:
            self.medium += 1
        elif score >= 0.40:
            self.low += 1
        else:
            self.very_low += 1

    def get_summary(self) -> dict[str, Any]:
        """Get distribution summary."""
        total = self.very_high + self.high + self.medium + self.low + self.very_low
        if total == 0:
            return {}

        return {
            "very_high_pct": self.very_high / total,
            "high_pct": self.high / total,
            "medium_pct": self.medium / total,
            "low_pct": self.low / total,
            "very_low_pct": self.very_low / total,
            "counts": {
                "very_high": self.very_high,
                "high": self.high,
                "medium": self.medium,
                "low": self.low,
                "very_low": self.very_low,
            },
        }


class MatchingMetrics(BaseModel):
    """Comprehensive metrics for matching engine performance."""

    # Timing
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Match statistics
    total_emails_processed: int = 0
    total_matches: int = 0
    total_needs_review: int = 0
    total_rejected: int = 0
    total_no_candidates: int = 0

    # Candidate statistics
    total_candidates_retrieved: int = 0
    total_candidates_scored: int = 0
    avg_candidates_per_email: float = 0.0

    # Confidence metrics
    confidence_distribution: ConfidenceDistribution = Field(
        default_factory=ConfidenceDistribution
    )
    avg_match_confidence: float = 0.0
    min_match_confidence: float = 1.0
    max_match_confidence: float = 0.0

    # Rule contributions
    rule_contributions: dict[str, RuleContribution] = Field(default_factory=dict)

    # Accuracy (if ground truth available)
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    def add_match_result(self, result: MatchResult) -> None:
        """
        Add a match result to metrics.

        Args:
            result: Match result to track
        """
        self.total_emails_processed += 1
        self.last_updated = datetime.now(timezone.utc)

        # Update status counts
        if result.match_status == "auto_matched":
            self.total_matches += 1
        elif result.match_status == "needs_review":
            self.total_needs_review += 1
        elif result.match_status == "rejected":
            self.total_rejected += 1
        elif result.match_status == "no_candidates":
            self.total_no_candidates += 1

        # Update candidate statistics
        self.total_candidates_retrieved += result.total_candidates_retrieved
        self.total_candidates_scored += result.total_candidates_scored

        if self.total_emails_processed > 0:
            self.avg_candidates_per_email = (
                self.total_candidates_retrieved / self.total_emails_processed
            )

        # Update confidence metrics
        if result.matched and result.best_candidate:
            confidence = result.confidence

            self.confidence_distribution.add_score(confidence)

            # Update aggregate confidence metrics
            if self.total_matches == 1:
                self.avg_match_confidence = confidence
                self.min_match_confidence = confidence
                self.max_match_confidence = confidence
            else:
                # Incremental average
                self.avg_match_confidence = (
                    self.avg_match_confidence * (self.total_matches - 1) + confidence
                ) / self.total_matches
                self.min_match_confidence = min(self.min_match_confidence, confidence)
                self.max_match_confidence = max(self.max_match_confidence, confidence)

            # Track rule contributions
            for rule_score in result.best_candidate.rule_scores:
                rule_name = rule_score.rule_name

                if rule_name not in self.rule_contributions:
                    self.rule_contributions[rule_name] = RuleContribution(
                        rule_name=rule_name
                    )

                self.rule_contributions[rule_name].update(rule_score.score)

    def add_batch_result(self, batch: BatchMatchResult) -> None:
        """
        Add batch results to metrics.

        Args:
            batch: Batch match result
        """
        for result in batch.results:
            self.add_match_result(result)

    def add_ground_truth(self, predicted_match: bool, actual_match: bool) -> None:
        """
        Add ground truth for accuracy calculation.

        Args:
            predicted_match: Whether engine predicted a match
            actual_match: Whether there was actually a match
        """
        if predicted_match and actual_match:
            self.true_positives += 1
        elif predicted_match and not actual_match:
            self.false_positives += 1
        elif not predicted_match and actual_match:
            self.false_negatives += 1
        else:
            self.true_negatives += 1

    def get_accuracy_metrics(self) -> dict[str, float]:
        """
        Calculate accuracy, precision, recall, F1.

        Returns:
            Dictionary of accuracy metrics
        """
        tp = self.true_positives
        fp = self.false_positives
        tn = self.true_negatives
        fn = self.false_negatives

        total = tp + fp + tn + fn

        if total == 0:
            return {
                "accuracy": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0,
            }

        accuracy = (tp + tn) / total if total > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_score = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
        }

    def get_summary(self) -> dict[str, Any]:
        """
        Get comprehensive metrics summary.

        Returns:
            Dictionary of all metrics
        """
        summary = {
            "timing": {
                "started_at": self.started_at.isoformat(),
                "last_updated": self.last_updated.isoformat(),
                "duration_seconds": (
                    self.last_updated - self.started_at
                ).total_seconds(),
            },
            "matching": {
                "total_emails": self.total_emails_processed,
                "matched": self.total_matches,
                "needs_review": self.total_needs_review,
                "rejected": self.total_rejected,
                "no_candidates": self.total_no_candidates,
                "match_rate": (
                    self.total_matches / self.total_emails_processed
                    if self.total_emails_processed > 0
                    else 0.0
                ),
            },
            "candidates": {
                "total_retrieved": self.total_candidates_retrieved,
                "total_scored": self.total_candidates_scored,
                "avg_per_email": self.avg_candidates_per_email,
            },
            "confidence": {
                "average": self.avg_match_confidence,
                "min": self.min_match_confidence,
                "max": self.max_match_confidence,
                "distribution": self.confidence_distribution.get_summary(),
            },
            "rules": {
                name: {
                    "avg_score": contrib.avg_score,
                    "max_score": contrib.max_score,
                    "min_score": contrib.min_score,
                    "high_scores": contrib.high_scores,
                    "invocations": contrib.total_invocations,
                }
                for name, contrib in self.rule_contributions.items()
            },
        }

        # Add accuracy metrics if available
        accuracy = self.get_accuracy_metrics()
        if accuracy["accuracy"] > 0:
            summary["accuracy"] = accuracy

        return summary

    def print_summary(self) -> None:
        """Print formatted metrics summary to console."""
        summary = self.get_summary()

        print("\n=== Matching Engine Metrics ===\n")

        print(f"Total Emails Processed: {self.total_emails_processed}")
        print(
            f"  ✓ Matched: {self.total_matches} ({summary['matching']['match_rate']:.1%})"
        )
        print(f"  ⚠ Needs Review: {self.total_needs_review}")
        print(f"  ✗ Rejected: {self.total_rejected}")
        print(f"  - No Candidates: {self.total_no_candidates}")

        print(f"\nAvg Candidates per Email: {self.avg_candidates_per_email:.1f}")

        print("\nConfidence Distribution:")
        dist = self.confidence_distribution.get_summary()
        if dist:
            print(
                f"  Very High (≥0.90): {dist['counts']['very_high']} ({dist['very_high_pct']:.1%})"
            )
            print(
                f"  High (0.80-0.89): {dist['counts']['high']} ({dist['high_pct']:.1%})"
            )
            print(
                f"  Medium (0.60-0.79): {dist['counts']['medium']} ({dist['medium_pct']:.1%})"
            )
            print(f"  Low (0.40-0.59): {dist['counts']['low']} ({dist['low_pct']:.1%})")
            print(
                f"  Very Low (<0.40): {dist['counts']['very_low']} ({dist['very_low_pct']:.1%})"
            )

        print("\nTop Contributing Rules:")
        sorted_rules = sorted(
            self.rule_contributions.items(), key=lambda x: x[1].avg_score, reverse=True
        )
        for name, contrib in sorted_rules[:5]:
            print(f"  {name}: avg={contrib.avg_score:.3f}, max={contrib.max_score:.3f}")

        # Print accuracy if available
        accuracy = self.get_accuracy_metrics()
        if accuracy["accuracy"] > 0:
            print("\nAccuracy Metrics:")
            print(f"  Accuracy: {accuracy['accuracy']:.1%}")
            print(f"  Precision: {accuracy['precision']:.1%}")
            print(f"  Recall: {accuracy['recall']:.1%}")
            print(f"  F1 Score: {accuracy['f1_score']:.3f}")

        print("\n" + "=" * 35 + "\n")


# Global metrics instance
_global_metrics = MatchingMetrics()


def get_metrics() -> MatchingMetrics:
    """Get global metrics instance."""
    return _global_metrics


def reset_metrics() -> None:
    """Reset global metrics."""
    global _global_metrics
    _global_metrics = MatchingMetrics()
    logger.info("Matching metrics reset")
