"""Fuzzy string matching utilities using rapidfuzz."""

from __future__ import annotations

import logging
from typing import Any

from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

from app.matching.config import FuzzyMatchConfig

logger = logging.getLogger(__name__)


class FuzzyMatcher:
    """Fuzzy string matching using rapidfuzz."""
    
    def __init__(self, config: FuzzyMatchConfig | None = None):
        """
        Initialize fuzzy matcher.
        
        Args:
            config: Fuzzy matching configuration
        """
        self.config = config or FuzzyMatchConfig()
        
    def simple_ratio(self, str1: str | None, str2: str | None) -> float:
        """
        Calculate simple Levenshtein ratio between two strings.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity ratio (0-1)
        """
        if not str1 or not str2:
            return 0.0
            
        score = fuzz.ratio(str1, str2) / 100.0
        return score if score >= self.config.min_similarity else 0.0
        
    def partial_ratio(self, str1: str | None, str2: str | None) -> float:
        """
        Calculate partial ratio (substring matching).
        
        Useful when one string is a substring of another.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity ratio (0-1)
        """
        if not str1 or not str2:
            return 0.0
            
        if not self.config.use_partial_ratio:
            return self.simple_ratio(str1, str2)
            
        score = fuzz.partial_ratio(str1, str2) / 100.0
        return score if score >= self.config.min_similarity else 0.0
        
    def token_sort_ratio(self, str1: str | None, str2: str | None) -> float:
        """
        Calculate token sort ratio (order-independent).
        
        Useful for matching strings with same words in different order.
        Example: "GTB Transfer 2025" matches "Transfer 2025 GTB"
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity ratio (0-1)
        """
        if not str1 or not str2:
            return 0.0
            
        if not self.config.use_token_sort:
            return self.simple_ratio(str1, str2)
            
        score = fuzz.token_sort_ratio(str1, str2) / 100.0
        return score if score >= self.config.min_similarity else 0.0
        
    def token_set_ratio(self, str1: str | None, str2: str | None) -> float:
        """
        Calculate token set ratio (handles common/different tokens).
        
        Best for strings with overlapping and unique tokens.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            Similarity ratio (0-1)
        """
        if not str1 or not str2:
            return 0.0
            
        score = fuzz.token_set_ratio(str1, str2) / 100.0
        return score if score >= self.config.min_similarity else 0.0
        
    def best_match(self, query: str, choices: list[str], scorer: str = "token_sort") -> tuple[str | None, float]:
        """
        Find best match from a list of choices.
        
        Args:
            query: String to match
            choices: List of candidate strings
            scorer: Scoring method ("simple", "partial", "token_sort", "token_set")
            
        Returns:
            Tuple of (best_match, score)
        """
        if not query or not choices:
            return None, 0.0
            
        # Map scorer name to function
        scorer_map = {
            "simple": fuzz.ratio,
            "partial": fuzz.partial_ratio,
            "token_sort": fuzz.token_sort_ratio,
            "token_set": fuzz.token_set_ratio,
        }
        
        scorer_func = scorer_map.get(scorer, fuzz.token_sort_ratio)
        
        # Use rapidfuzz's process.extractOne for efficient matching
        result = process.extractOne(query, choices, scorer=scorer_func)
        
        if result:
            best_match, score, _ = result
            normalized_score = score / 100.0
            
            if normalized_score >= self.config.min_similarity:
                return best_match, normalized_score
                
        return None, 0.0
        
    def match_tokens(self, tokens1: list[str], tokens2: list[str]) -> float:
        """
        Match two lists of tokens and return similarity score.
        
        Calculates what percentage of tokens from tokens1 have a good match in tokens2.
        
        Args:
            tokens1: First list of tokens
            tokens2: Second list of tokens
            
        Returns:
            Match score (0-1)
        """
        if not tokens1 or not tokens2:
            return 0.0
            
        # Filter short tokens
        tokens1_filtered = [t for t in tokens1 if len(t) >= self.config.min_token_length]
        tokens2_filtered = [t for t in tokens2 if len(t) >= self.config.min_token_length]
        
        if not tokens1_filtered or not tokens2_filtered:
            return 0.0
            
        # Count how many tokens from tokens1 have a good match in tokens2
        matched_count = 0
        total_score = 0.0
        
        for token1 in tokens1_filtered:
            best_match, score = self.best_match(token1, tokens2_filtered, scorer="simple")
            if best_match and score >= self.config.min_similarity:
                matched_count += 1
                total_score += score
                
        if matched_count == 0:
            return 0.0
            
        # Average score of matched tokens, weighted by match rate
        avg_score = total_score / matched_count
        match_rate = matched_count / len(tokens1_filtered)
        
        return avg_score * match_rate
        
    def comprehensive_similarity(
        self,
        str1: str | None,
        str2: str | None,
        weights: dict[str, float] | None = None
    ) -> dict[str, Any]:
        """
        Calculate comprehensive similarity using multiple methods.
        
        Args:
            str1: First string
            str2: Second string
            weights: Optional weights for each method (default: equal weights)
            
        Returns:
            Dictionary with individual scores and weighted average
        """
        if not str1 or not str2:
            return {
                "simple": 0.0,
                "partial": 0.0,
                "token_sort": 0.0,
                "token_set": 0.0,
                "weighted_average": 0.0,
                "max_score": 0.0,
            }
            
        # Default equal weights
        if weights is None:
            weights = {
                "simple": 0.25,
                "partial": 0.25,
                "token_sort": 0.25,
                "token_set": 0.25,
            }
            
        scores = {
            "simple": self.simple_ratio(str1, str2),
            "partial": self.partial_ratio(str1, str2),
            "token_sort": self.token_sort_ratio(str1, str2),
            "token_set": self.token_set_ratio(str1, str2),
        }
        
        # Calculate weighted average
        weighted_avg = sum(scores[k] * weights.get(k, 0.25) for k in scores)
        
        scores["weighted_average"] = weighted_avg
        scores["max_score"] = max(scores["simple"], scores["partial"], scores["token_sort"], scores["token_set"])
        
        return scores
        
    def is_high_similarity(self, str1: str | None, str2: str | None) -> bool:
        """
        Check if two strings have high similarity.
        
        Args:
            str1: First string
            str2: Second string
            
        Returns:
            True if similarity >= high_similarity threshold
        """
        if not str1 or not str2:
            return False
            
        score = self.token_sort_ratio(str1, str2)
        return score >= self.config.high_similarity


# Convenience functions
def quick_ratio(str1: str | None, str2: str | None, min_similarity: float = 0.6) -> float:
    """
    Quick similarity ratio (convenience function).
    
    Args:
        str1: First string
        str2: Second string
        min_similarity: Minimum similarity threshold
        
    Returns:
        Similarity score (0-1)
    """
    if not str1 or not str2:
        return 0.0
        
    score = fuzz.token_sort_ratio(str1, str2) / 100.0
    return score if score >= min_similarity else 0.0


def match_reference(ref1: str | None, ref2: str | None) -> float:
    """
    Match two reference strings (optimized for transaction references).
    
    Args:
        ref1: First reference
        ref2: Second reference
        
    Returns:
        Match score (0-1)
    """
    matcher = FuzzyMatcher()
    
    # Use comprehensive similarity
    result = matcher.comprehensive_similarity(ref1, ref2)
    
    # Return the maximum score (most lenient)
    return result["max_score"]


def match_sender_name(name1: str | None, name2: str | None) -> float:
    """
    Match two sender names.
    
    Args:
        name1: First name
        name2: Second name
        
    Returns:
        Match score (0-1)
    """
    matcher = FuzzyMatcher()
    
    # Use token sort (order independent)
    return matcher.token_sort_ratio(name1, name2)
