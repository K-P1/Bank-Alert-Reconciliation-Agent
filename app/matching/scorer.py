"""Scoring and ranking for match candidates."""

from __future__ import annotations

import logging
from typing import Literal

from app.matching.config import MatchingConfig
from app.matching.models import MatchCandidate, MatchResult
from app.matching.rules import MatchingRules
from app.normalization.models import NormalizedEmail, NormalizedTransaction

logger = logging.getLogger(__name__)


class MatchScorer:
    """Scores and ranks match candidates."""
    
    def __init__(self, config: MatchingConfig | None = None):
        """
        Initialize match scorer.
        
        Args:
            config: Matching configuration
        """
        self.config = config or MatchingConfig()
        self.rules = MatchingRules(self.config)
        
    def score_candidate(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> MatchCandidate:
        """
        Score a single candidate transaction against an email.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Scored match candidate
        """
        # Create candidate object
        candidate = MatchCandidate(
            transaction_id=0,  # Will be set from DB
            external_transaction_id=transaction.transaction_id,
            amount=transaction.amount,
            currency=transaction.currency,
            timestamp=transaction.timestamp,
            reference=transaction.reference.original if transaction.reference else None,
            account_ref=transaction.account_ref,
            description=transaction.description,
        )
        
        # Apply all matching rules
        weights = self.config.rule_weights
        
        # 1. Exact amount match
        score, details = self.rules.exact_amount_match(email, transaction)
        candidate.add_rule_score("exact_amount", score, weights.exact_amount, details)
        
        # 2. Exact reference match
        score, details = self.rules.exact_reference_match(email, transaction)
        candidate.add_rule_score("exact_reference", score, weights.exact_reference, details)
        
        # 3. Fuzzy reference match
        score, details = self.rules.fuzzy_reference_match(email, transaction)
        candidate.add_rule_score("fuzzy_reference", score, weights.fuzzy_reference, details)
        
        # 4. Timestamp proximity
        score, details = self.rules.timestamp_proximity(email, transaction)
        candidate.add_rule_score("timestamp_proximity", score, weights.timestamp_proximity, details)
        
        # 5. Account match
        score, details = self.rules.account_match(email, transaction)
        candidate.add_rule_score("account_match", score, weights.account_match, details)
        
        # 6. Composite key match
        score, details = self.rules.composite_key_match(email, transaction)
        candidate.add_rule_score("composite_key", score, weights.composite_key, details)
        
        # 7. Bank match
        score, details = self.rules.bank_match(email, transaction)
        candidate.add_rule_score("bank_match", score, weights.bank_match, details)
        
        # Log scoring if debug enabled
        if self.config.debug:
            logger.debug(
                f"Scored candidate {transaction.transaction_id}: {candidate.total_score:.4f}",
                extra={
                    "email_id": email.message_id,
                    "transaction_id": transaction.transaction_id,
                    "total_score": candidate.total_score,
                    "breakdown": candidate.get_score_breakdown(),
                }
            )
            
        return candidate
        
    def score_all_candidates(
        self,
        email: NormalizedEmail,
        transactions: list[NormalizedTransaction]
    ) -> list[MatchCandidate]:
        """
        Score all candidate transactions.
        
        Args:
            email: Normalized email
            transactions: List of candidate transactions
            
        Returns:
            List of scored candidates
        """
        candidates = []
        
        for transaction in transactions:
            try:
                candidate = self.score_candidate(email, transaction)
                candidates.append(candidate)
            except Exception as e:
                logger.error(
                    f"Failed to score candidate {transaction.transaction_id}: {e}",
                    exc_info=True
                )
                continue
                
        logger.info(
            f"Scored {len(candidates)} candidates for email {email.message_id}",
            extra={
                "email_id": email.message_id,
                "total_candidates": len(candidates),
                "avg_score": sum(c.total_score for c in candidates) / len(candidates) if candidates else 0,
            }
        )
        
        return candidates
        
    def rank_candidates(
        self,
        candidates: list[MatchCandidate]
    ) -> list[MatchCandidate]:
        """
        Rank candidates by score (highest first).
        
        Args:
            candidates: List of scored candidates
            
        Returns:
            Ranked candidates
        """
        # Sort by total score (descending)
        ranked = sorted(candidates, key=lambda c: c.total_score, reverse=True)
        
        # Assign ranks
        for i, candidate in enumerate(ranked, start=1):
            candidate.rank = i
            
        return ranked
        
    def apply_tie_breaking(
        self,
        candidates: list[MatchCandidate],
        email: NormalizedEmail
    ) -> list[MatchCandidate]:
        """
        Apply tie-breaking rules when multiple candidates have similar scores.
        
        Args:
            candidates: Ranked candidates
            email: Original email
            
        Returns:
            Candidates with tie-breaking applied
        """
        if not candidates:
            return candidates
            
        tie_config = self.config.tie_breaking
        max_diff = tie_config.max_tie_difference
        
        # Group candidates within tie threshold
        best_score = candidates[0].total_score
        tied_candidates = [c for c in candidates if best_score - c.total_score <= max_diff]
        
        if len(tied_candidates) <= 1:
            # No ties
            return candidates
            
        logger.info(
            f"Found {len(tied_candidates)} tied candidates, applying tie-breaking",
            extra={
                "best_score": best_score,
                "tie_threshold": max_diff,
            }
        )
        
        # Apply tie-breaking preferences
        for candidate in tied_candidates:
            tie_score = 0.0
            
            # Prefer more recent transactions
            if tie_config.prefer_recent and email.timestamp:
                hours_diff = abs((candidate.timestamp - email.timestamp).total_seconds()) / 3600
                recency_score = 1.0 / (1.0 + hours_diff)  # Exponential decay
                tie_score += recency_score * 0.4
                
            # Prefer high reference similarity
            if tie_config.prefer_high_reference_similarity:
                # Find reference similarity score from rules
                ref_scores = [
                    rs.score for rs in candidate.rule_scores
                    if rs.rule_name in ("exact_reference", "fuzzy_reference")
                ]
                if ref_scores:
                    tie_score += max(ref_scores) * 0.4
                    
            # Prefer same bank
            if tie_config.prefer_same_bank:
                bank_scores = [
                    rs.score for rs in candidate.rule_scores
                    if rs.rule_name == "bank_match"
                ]
                if bank_scores:
                    tie_score += max(bank_scores) * 0.2
                    
            # Store tie-breaking score
            candidate.total_score += tie_score * 0.01  # Small adjustment
            
        # Re-rank after tie-breaking
        return self.rank_candidates(candidates)
        
    def determine_match_status(
        self,
        best_candidate: MatchCandidate | None
    ) -> Literal["auto_matched", "needs_review", "rejected", "no_candidates"]:
        """
        Determine match status based on confidence thresholds.
        
        Args:
            best_candidate: Best scoring candidate
            
        Returns:
            Match status
        """
        if best_candidate is None:
            return "no_candidates"
            
        thresholds = self.config.thresholds
        confidence = best_candidate.total_score
        
        if confidence >= thresholds.auto_match:
            return "auto_matched"
        elif confidence >= thresholds.needs_review:
            return "needs_review"
        else:
            return "rejected"
            
    def create_match_result(
        self,
        email: NormalizedEmail,
        email_db_id: int,
        candidates: list[MatchCandidate]
    ) -> MatchResult:
        """
        Create a match result from scored and ranked candidates.
        
        Args:
            email: Original email
            email_db_id: Database ID of email
            candidates: Scored and ranked candidates
            
        Returns:
            Match result
        """
        result = MatchResult(
            email_id=email_db_id,
            email_message_id=email.message_id,
            total_candidates_retrieved=len(candidates),
            total_candidates_scored=len(candidates),
            matching_method="hybrid",
            match_status="needs_review",  # Will be updated based on scores
        )
        
        if not candidates:
            result.match_status = "no_candidates"
            result.add_note("No candidate transactions found")
            return result
            
        # Rank candidates
        ranked = self.rank_candidates(candidates)
        
        # Apply tie-breaking
        ranked = self.apply_tie_breaking(ranked, email)
        
        # Get best candidate
        best_candidate = ranked[0]
        
        # Determine status
        status = self.determine_match_status(best_candidate)
        
        result.match_status = status
        
        if status in ("auto_matched", "needs_review"):
            result.set_best_match(best_candidate)
            
            # Store alternatives
            if self.config.store_alternatives and len(ranked) > 1:
                max_alt = self.config.max_alternatives
                result.alternative_candidates = ranked[1:max_alt+1]
                
        elif status == "rejected":
            result.add_note(
                f"Best candidate score {best_candidate.total_score:.4f} below threshold "
                f"{self.config.thresholds.needs_review:.4f}"
            )
            
            # Still store as alternative for manual review
            if self.config.store_alternatives:
                result.alternative_candidates = ranked[:self.config.max_alternatives]
                
        # Add statistics
        if candidates:
            avg_score = sum(c.total_score for c in candidates) / len(candidates)
            result.add_note(f"Average candidate score: {avg_score:.4f}")
            result.add_note(f"Best candidate score: {best_candidate.total_score:.4f}")
            
        logger.info(
            f"Created match result for email {email.message_id}",
            extra={
                "email_id": email_db_id,
                "status": status,
                "matched": result.matched,
                "confidence": result.confidence,
                "candidates": len(candidates),
            }
        )
        
        return result


# Convenience function
def score_and_rank(
    email: NormalizedEmail,
    transactions: list[NormalizedTransaction],
    config: MatchingConfig | None = None
) -> list[MatchCandidate]:
    """
    Score and rank candidate transactions.
    
    Args:
        email: Normalized email
        transactions: Candidate transactions
        config: Matching configuration
        
    Returns:
        Ranked candidates
    """
    scorer = MatchScorer(config)
    candidates = scorer.score_all_candidates(email, transactions)
    return scorer.rank_candidates(candidates)
