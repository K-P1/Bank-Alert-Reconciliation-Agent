"""Individual matching rules for transaction reconciliation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from app.matching.config import MatchingConfig, TimeWindowConfig, FuzzyMatchConfig
from app.matching.fuzzy import FuzzyMatcher
from app.normalization.models import NormalizedEmail, NormalizedTransaction

logger = logging.getLogger(__name__)


class MatchingRules:
    """Collection of matching rules for transaction reconciliation."""
    
    def __init__(self, config: MatchingConfig | None = None):
        """
        Initialize matching rules.
        
        Args:
            config: Matching configuration
        """
        self.config = config or MatchingConfig()
        self.fuzzy_matcher = FuzzyMatcher(self.config.fuzzy_match)
        
    def exact_amount_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Check if amounts match exactly.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details = {
            "email_amount": str(email.amount) if email.amount else None,
            "transaction_amount": str(transaction.amount),
            "match_type": "none"
        }
        
        if email.amount is None:
            details["match_type"] = "missing_email_amount"
            return 0.0, details
            
        # Exact match
        if email.amount == transaction.amount:
            details["match_type"] = "exact"
            return 1.0, details
            
        # Check with tolerance (for floating point imprecision)
        tolerance = self.config.candidate_retrieval.amount_tolerance_percent
        diff = abs(email.amount - transaction.amount)
        max_diff = email.amount * Decimal(str(tolerance))
        
        if diff <= max_diff:
            details["match_type"] = "within_tolerance"
            details["difference"] = str(diff)
            details["tolerance"] = str(max_diff)
            return 0.95, details
            
        details["match_type"] = "mismatch"
        details["difference"] = str(diff)
        return 0.0, details
        
    def currency_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Check if currencies match.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details = {
            "email_currency": email.currency,
            "transaction_currency": transaction.currency
        }
        
        if email.currency is None:
            details["match_type"] = "missing_email_currency"
            return 0.5, details  # Neutral score if currency not in email
            
        if email.currency == transaction.currency:
            details["match_type"] = "exact"
            return 1.0, details
            
        details["match_type"] = "mismatch"
        return 0.0, details
        
    def exact_reference_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Check for exact reference match.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details = {
            "email_reference": email.reference.original if email.reference else None,
            "transaction_reference": transaction.reference.original if transaction.reference else None,
            "match_type": "none"
        }
        
        if not email.reference or not transaction.reference:
            details["match_type"] = "missing_reference"
            return 0.0, details
            
        # Check alphanumeric-only version (ignore punctuation)
        if email.reference.alphanumeric_only == transaction.reference.alphanumeric_only:
            details["match_type"] = "exact_alphanumeric"
            return 1.0, details
            
        # Check cleaned version
        if email.reference.cleaned == transaction.reference.cleaned:
            details["match_type"] = "exact_cleaned"
            return 0.95, details
            
        details["match_type"] = "no_exact_match"
        return 0.0, details
        
    def fuzzy_reference_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Check for fuzzy reference match using string similarity.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details: dict[str, Any] = {
            "email_reference": email.reference.original if email.reference else None,
            "transaction_reference": transaction.reference.original if transaction.reference else None,
        }
        
        if not email.reference or not transaction.reference:
            details["similarity_score"] = 0.0
            return 0.0, details
            
        # Try comprehensive similarity on cleaned references
        similarity = self.fuzzy_matcher.comprehensive_similarity(
            email.reference.cleaned,
            transaction.reference.cleaned
        )
        
        details["similarity_scores"] = similarity
        details["best_score"] = similarity["max_score"]
        
        # Use max score as the rule score
        return similarity["max_score"], details
        
    def token_reference_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Match reference tokens.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details: dict[str, Any] = {
            "email_tokens": email.reference.tokens if email.reference else [],
            "transaction_tokens": transaction.reference.tokens if transaction.reference else [],
        }
        
        if not email.reference or not transaction.reference:
            details["token_match_score"] = 0.0
            return 0.0, details
            
        score = self.fuzzy_matcher.match_tokens(
            email.reference.tokens,
            transaction.reference.tokens
        )
        
        details["token_match_score"] = score
        details["common_tokens"] = list(set(email.reference.tokens) & set(transaction.reference.tokens))
        
        return score, details
        
    def timestamp_proximity(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction,
        time_window_hours: int | None = None
    ) -> tuple[float, dict[str, Any]]:
        """
        Score based on timestamp proximity.
        
        Closer timestamps get higher scores. Uses exponential decay.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            time_window_hours: Custom time window (default: from config)
            
        Returns:
            Tuple of (score, details)
        """
        details = {
            "email_timestamp": email.timestamp.isoformat() if email.timestamp else None,
            "transaction_timestamp": transaction.timestamp.isoformat(),
        }
        
        if email.timestamp is None:
            details["score"] = 0.5  # Neutral if no timestamp
            return 0.5, details
            
        # Calculate time difference
        time_diff = abs((email.timestamp - transaction.timestamp).total_seconds())
        hours_diff = time_diff / 3600
        
        details["hours_difference"] = hours_diff
        
        # Use configured time window
        if time_window_hours is None:
            time_window_hours = self.config.time_window.default_hours
            
        details["time_window_hours"] = time_window_hours
        
        # Perfect match within 1 hour
        if hours_diff <= 1:
            details["proximity"] = "within_1_hour"
            return 1.0, details
            
        # Linear decay within time window
        if hours_diff <= time_window_hours:
            score = 1.0 - (hours_diff / time_window_hours)
            details["proximity"] = "within_window"
            details["score"] = score
            return score, details
            
        # Outside time window
        details["proximity"] = "outside_window"
        details["score"] = 0.0
        return 0.0, details
        
    def account_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Match account numbers (last 4 digits).
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details: dict[str, Any] = {
            "email_account": email.account_number,
            "transaction_account": transaction.account_ref,
        }
        
        if not email.account_number or not transaction.account_ref:
            details["match_type"] = "missing_account"
            return 0.0, details
            
        # Extract last 4 digits
        email_last4 = email.account_number[-4:] if len(email.account_number) >= 4 else email.account_number
        txn_last4 = transaction.account_ref[-4:] if len(transaction.account_ref) >= 4 else transaction.account_ref
        
        details["email_last4"] = email_last4
        details["transaction_last4"] = txn_last4
        
        if email_last4 == txn_last4:
            details["match_type"] = "exact_last4"
            return 1.0, details
            
        # Try full account number match
        if email.account_number == transaction.account_ref:
            details["match_type"] = "exact_full"
            return 1.0, details
            
        # Fuzzy match on full account
        similarity = self.fuzzy_matcher.simple_ratio(email.account_number, transaction.account_ref)
        details["similarity"] = similarity
        
        if similarity >= 0.8:
            details["match_type"] = "fuzzy"
            return similarity, details
            
        details["match_type"] = "mismatch"
        return 0.0, details
        
    def composite_key_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Match using composite keys.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details: dict[str, Any] = {
            "email_key": email.composite_key.to_string() if email.composite_key else None,
            "transaction_key": transaction.composite_key.to_string() if transaction.composite_key else None,
        }
        
        if not email.composite_key or not transaction.composite_key:
            details["match_type"] = "missing_key"
            return 0.0, details
            
        # Exact match
        if email.composite_key.to_string() == transaction.composite_key.to_string():
            details["match_type"] = "exact"
            return 1.0, details
            
        # Partial match: same amount, currency, date bucket
        partial_matches = 0
        total_components = 5
        
        if email.composite_key.amount_str == transaction.composite_key.amount_str:
            partial_matches += 1
            details["amount_match"] = True
            
        if email.composite_key.currency == transaction.composite_key.currency:
            partial_matches += 1
            details["currency_match"] = True
            
        if email.composite_key.date_bucket == transaction.composite_key.date_bucket:
            partial_matches += 1
            details["date_bucket_match"] = True
            
        # Check reference tokens overlap
        email_tokens = set(email.composite_key.reference_tokens)
        txn_tokens = set(transaction.composite_key.reference_tokens)
        
        if email_tokens and txn_tokens:
            token_overlap = len(email_tokens & txn_tokens) / max(len(email_tokens), len(txn_tokens))
            details["token_overlap"] = token_overlap
            if token_overlap > 0.5:
                partial_matches += token_overlap
        
        # Check account last4
        if email.composite_key.account_last4 and transaction.composite_key.account_last4:
            if email.composite_key.account_last4 == transaction.composite_key.account_last4:
                partial_matches += 1
                details["account_match"] = True
                
        score = partial_matches / total_components
        details["match_type"] = "partial"
        details["partial_score"] = score
        
        return score, details
        
    def bank_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Match bank information from enrichment.
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details: dict[str, Any] = {
            "email_bank": email.enrichment.bank_code if email.enrichment else None,
            "transaction_bank": transaction.enrichment.bank_code if transaction.enrichment else None,
        }
        
        if not email.enrichment or not transaction.enrichment:
            details["match_type"] = "no_enrichment"
            return 0.0, details
            
        if not email.enrichment.bank_code or not transaction.enrichment.bank_code:
            details["match_type"] = "missing_bank_code"
            return 0.0, details
            
        if email.enrichment.bank_code == transaction.enrichment.bank_code:
            details["match_type"] = "exact"
            # Weight by enrichment confidence
            avg_confidence = (email.enrichment.enrichment_confidence + transaction.enrichment.enrichment_confidence) / 2
            score = 1.0 * avg_confidence
            details["enrichment_confidence"] = avg_confidence
            return score, details
            
        details["match_type"] = "mismatch"
        return 0.0, details
        
    def transaction_type_match(
        self,
        email: NormalizedEmail,
        transaction: NormalizedTransaction
    ) -> tuple[float, dict[str, Any]]:
        """
        Match transaction type (credit/debit).
        
        Args:
            email: Normalized email
            transaction: Normalized transaction
            
        Returns:
            Tuple of (score, details)
        """
        details = {
            "email_type": email.transaction_type,
            "transaction_type": transaction.transaction_type,
        }
        
        if not email.transaction_type or not transaction.transaction_type:
            details["match_type"] = "missing_type"
            return 0.5, details  # Neutral
            
        if email.transaction_type == transaction.transaction_type:
            details["match_type"] = "exact"
            return 1.0, details
            
        details["match_type"] = "mismatch"
        return 0.0, details
