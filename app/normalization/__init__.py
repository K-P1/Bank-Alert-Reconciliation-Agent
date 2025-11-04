"""Normalization and enrichment module for transaction data."""

from app.normalization.models import (
    NormalizedEmail,
    NormalizedTransaction,
    EnrichmentMetadata,
    CompositeKey,
)
from app.normalization.normalizer import (
    normalize_amount,
    normalize_currency,
    normalize_timestamp,
    normalize_reference,
    enrich_bank_info,
    create_composite_key,
    normalize_email,
    normalize_transaction,
)

__all__ = [
    # Models
    "NormalizedEmail",
    "NormalizedTransaction",
    "EnrichmentMetadata",
    "CompositeKey",
    # Functions
    "normalize_amount",
    "normalize_currency",
    "normalize_timestamp",
    "normalize_reference",
    "enrich_bank_info",
    "create_composite_key",
    "normalize_email",
    "normalize_transaction",
]
