"""Email fetcher and parser module for Bank Alert Reconciliation Agent.

This module handles:
- IMAP email fetching
- Rule-based pre-filtering
- LLM-assisted classification and extraction
- Regex-based fallback extraction
- Hybrid parsing pipeline
"""

# Lazy imports to avoid circular dependencies
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.emails.config import EmailConfig, FetcherConfig, FilterConfig, LLMConfig, ParserConfig
    from app.emails.fetcher import EmailFetcher
    from app.emails.parser import HybridParser

__all__ = [
    "EmailConfig",
    "FetcherConfig",
    "FilterConfig",
    "LLMConfig",
    "ParserConfig",
    "EmailFetcher",
    "HybridParser",
]
