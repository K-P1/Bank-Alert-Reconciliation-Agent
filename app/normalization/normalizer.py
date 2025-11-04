"""Core normalization and enrichment functions."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.normalization.models import (
    NormalizedEmail,
    NormalizedTransaction,
    NormalizedReference,
    EnrichmentMetadata,
    CompositeKey,
)
from app.emails.models import ParsedEmail

logger = logging.getLogger(__name__)


# ============================================================================
# Currency Mappings
# ============================================================================

CURRENCY_SYMBOLS = {
    "₦": "NGN",
    "$": "USD",
    "£": "GBP",
    "€": "EUR",
    "¥": "JPY",
}

# Nigerian bank codes and names
BANK_MAPPINGS = {
    # Access Bank
    "access": {"code": "ACC", "name": "Access Bank Plc", "domains": ["accessbankplc.com", "accessbank.com"]},
    "accessbank": {"code": "ACC", "name": "Access Bank Plc", "domains": ["accessbankplc.com", "accessbank.com"]},
    
    # GTBank (Guaranty Trust Bank)
    "gtb": {"code": "GTB", "name": "Guaranty Trust Bank", "domains": ["gtbank.com", "gtb.com"]},
    "gtbank": {"code": "GTB", "name": "Guaranty Trust Bank", "domains": ["gtbank.com", "gtb.com"]},
    "guaranty": {"code": "GTB", "name": "Guaranty Trust Bank", "domains": ["gtbank.com"]},
    
    # First Bank
    "firstbank": {"code": "FBN", "name": "First Bank of Nigeria", "domains": ["firstbanknigeria.com", "firstbank.com"]},
    "fbn": {"code": "FBN", "name": "First Bank of Nigeria", "domains": ["firstbanknigeria.com"]},
    
    # Zenith Bank
    "zenith": {"code": "ZEN", "name": "Zenith Bank Plc", "domains": ["zenithbank.com"]},
    "zenithbank": {"code": "ZEN", "name": "Zenith Bank Plc", "domains": ["zenithbank.com"]},
    
    # UBA (United Bank for Africa)
    "uba": {"code": "UBA", "name": "United Bank for Africa", "domains": ["ubagroup.com", "uba.com"]},
    "unitedbank": {"code": "UBA", "name": "United Bank for Africa", "domains": ["ubagroup.com"]},
    
    # FCMB (First City Monument Bank)
    "fcmb": {"code": "FCMB", "name": "First City Monument Bank", "domains": ["fcmb.com"]},
    
    # Stanbic IBTC
    "stanbic": {"code": "STANBIC", "name": "Stanbic IBTC Bank", "domains": ["stanbicibtc.com"]},
    "stanbicibtc": {"code": "STANBIC", "name": "Stanbic IBTC Bank", "domains": ["stanbicibtc.com"]},
    
    # Union Bank
    "union": {"code": "UNION", "name": "Union Bank of Nigeria", "domains": ["unionbank.com"]},
    "unionbank": {"code": "UNION", "name": "Union Bank of Nigeria", "domains": ["unionbank.com"]},
    
    # Ecobank
    "ecobank": {"code": "ECO", "name": "Ecobank Nigeria", "domains": ["ecobank.com"]},
    
    # Fidelity Bank
    "fidelity": {"code": "FID", "name": "Fidelity Bank Plc", "domains": ["fidelitybank.ng"]},
    "fidelitybank": {"code": "FID", "name": "Fidelity Bank Plc", "domains": ["fidelitybank.ng"]},
    
    # Sterling Bank
    "sterling": {"code": "STERLING", "name": "Sterling Bank Plc", "domains": ["sterling.ng", "sterlingbankng.com"]},
    "sterlingbank": {"code": "STERLING", "name": "Sterling Bank Plc", "domains": ["sterling.ng"]},
    
    # Wema Bank
    "wema": {"code": "WEMA", "name": "Wema Bank Plc", "domains": ["wemabank.com"]},
    "wemabank": {"code": "WEMA", "name": "Wema Bank Plc", "domains": ["wemabank.com"]},
    
    # Polaris Bank
    "polaris": {"code": "POLARIS", "name": "Polaris Bank", "domains": ["polarisbanklimited.com"]},
    "polarisbank": {"code": "POLARIS", "name": "Polaris Bank", "domains": ["polarisbanklimited.com"]},
    
    # Keystone Bank
    "keystone": {"code": "KEYSTONE", "name": "Keystone Bank", "domains": ["keystonebankng.com"]},
    "keystonebank": {"code": "KEYSTONE", "name": "Keystone Bank", "domains": ["keystonebankng.com"]},
    
    # Unity Bank
    "unity": {"code": "UNITY", "name": "Unity Bank Plc", "domains": ["unitybankng.com"]},
    "unitybank": {"code": "UNITY", "name": "Unity Bank Plc", "domains": ["unitybankng.com"]},
    
    # Heritage Bank
    "heritage": {"code": "HERITAGE", "name": "Heritage Bank", "domains": ["hbng.com"]},
    "heritagebank": {"code": "HERITAGE", "name": "Heritage Bank", "domains": ["hbng.com"]},
}


# ============================================================================
# Amount Normalization
# ============================================================================

def normalize_amount(amount_str: str | Decimal | float | int | None) -> Decimal | None:
    """
    Normalize amount to Decimal.
    
    Handles various formats:
    - "₦23,500.00" -> Decimal('23500.00')
    - "NGN 1,000" -> Decimal('1000.00')
    - "23500" -> Decimal('23500.00')
    - "$1,234.56" -> Decimal('1234.56')
    
    Args:
        amount_str: Amount in various formats
        
    Returns:
        Normalized Decimal amount or None if parsing fails
    """
    if amount_str is None:
        return None
    
    # Already a Decimal
    if isinstance(amount_str, Decimal):
        return amount_str
    
    # Numeric types
    if isinstance(amount_str, (int, float)):
        try:
            return Decimal(str(amount_str))
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Failed to convert numeric amount {amount_str}: {e}")
            return None
    
    # String processing
    try:
        # Remove currency symbols and codes
        cleaned = str(amount_str).strip()
        
        # Remove currency symbols
        for symbol in CURRENCY_SYMBOLS:
            cleaned = cleaned.replace(symbol, "")
        
        # Remove commas (thousand separators) BEFORE removing currency codes
        cleaned = cleaned.replace(",", "")
        
        # Remove common currency codes using a single regex pattern
        import re
        # Match currency codes that are NOT part of a larger word
        # The pattern matches the codes with optional surrounding whitespace
        cleaned = re.sub(r'\s*(NGN|USD|GBP|EUR|JPY)\s*', ' ', cleaned, flags=re.IGNORECASE)
        
        # Remove whitespace
        cleaned = cleaned.strip()
        
        # Handle empty string
        if not cleaned:
            return None
        
        # Convert to Decimal
        amount = Decimal(cleaned)
        
        # Round to 2 decimal places
        return amount.quantize(Decimal("0.01"))
        
    except Exception as e:
        logger.warning(f"Failed to normalize amount '{amount_str}': {type(e).__name__}: {e}. Cleaned value: '{cleaned if 'cleaned' in locals() else 'N/A'}'")
        return None


# ============================================================================
# Currency Normalization
# ============================================================================

def normalize_currency(currency_str: str | None) -> str | None:
    """
    Normalize currency to ISO 4217 code.
    
    Handles:
    - "₦" -> "NGN"
    - "naira" -> "NGN"
    - "NGN" -> "NGN"
    - "$" -> "USD"
    
    Args:
        currency_str: Currency in various formats
        
    Returns:
        ISO 4217 currency code or None
    """
    if currency_str is None:
        return None
    
    currency_str = str(currency_str).strip().upper()
    
    # Already ISO code
    if len(currency_str) == 3 and currency_str.isalpha():
        return currency_str
    
    # Symbol mapping
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in currency_str:
            return code
    
    # Name mapping (check full word matches)
    currency_names = {
        "NAIRA": "NGN",
        "NAIRAS": "NGN",
        "DOLLAR": "USD",
        "DOLLARS": "USD",
        "POUND": "GBP",
        "POUNDS": "GBP",
        "STERLING": "GBP",
        "EURO": "EUR",
        "EUROS": "EUR",
        "YEN": "JPY",
    }
    
    # Check for full word matches to avoid false positives
    import re
    for name, code in currency_names.items():
        if re.search(rf'\b{name}\b', currency_str):
            return code
    
    # Default to NGN for Nigerian context
    logger.debug(f"Could not normalize currency '{currency_str}', defaulting to NGN")
    return "NGN"


# ============================================================================
# Timestamp Normalization
# ============================================================================

def normalize_timestamp(
    timestamp: datetime | str | None,
    default_timezone: timezone = timezone.utc,
) -> datetime | None:
    """
    Normalize timestamp to UTC ISO 8601 format.
    
    Handles:
    - datetime objects (converted to UTC)
    - ISO 8601 strings
    - Common Nigerian formats: "04/11/2025 10:30:00", "2025-11-04 10:30"
    - Adds default timezone if naive
    
    Args:
        timestamp: Timestamp in various formats
        default_timezone: Timezone to assume for naive timestamps
        
    Returns:
        Normalized datetime in UTC or None
    """
    if timestamp is None:
        return None
    
    # Already a datetime
    if isinstance(timestamp, datetime):
        # Make timezone-aware if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=default_timezone)
        # Convert to UTC
        return timestamp.astimezone(timezone.utc)
    
    # String parsing
    try:
        timestamp_str = str(timestamp).strip()
        
        # Try ISO 8601 format
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=default_timezone)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
        
        # Try common formats
        formats = [
            "%d/%m/%Y %H:%M:%S",  # 04/11/2025 10:30:00
            "%d/%m/%Y %H:%M",     # 04/11/2025 10:30
            "%d-%m-%Y %H:%M:%S",  # 04-11-2025 10:30:00
            "%d-%m-%Y %H:%M",     # 04-11-2025 10:30
            "%Y-%m-%d %H:%M:%S",  # 2025-11-04 10:30:00
            "%Y-%m-%d %H:%M",     # 2025-11-04 10:30
            "%d %b %Y %H:%M:%S",  # 04 Nov 2025 10:30:00
            "%d %b %Y %H:%M",     # 04 Nov 2025 10:30
            "%d %B %Y %H:%M:%S",  # 04 November 2025 10:30:00
            "%d %B %Y %H:%M",     # 04 November 2025 10:30
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(timestamp_str, fmt)
                dt = dt.replace(tzinfo=default_timezone)
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue
        
        logger.warning(f"Could not parse timestamp '{timestamp_str}'")
        return None
        
    except Exception as e:
        logger.warning(f"Failed to normalize timestamp '{timestamp}': {e}")
        return None


# ============================================================================
# Reference Normalization
# ============================================================================

def normalize_reference(reference: str | None) -> NormalizedReference | None:
    """
    Normalize and tokenize reference string.
    
    Operations:
    - Strip whitespace and punctuation
    - Normalize whitespace
    - Extract alphanumeric tokens
    - Create searchable token list
    
    Args:
        reference: Original reference string
        
    Returns:
        NormalizedReference object or None
    """
    if reference is None:
        return None
    
    original = str(reference).strip()
    
    if not original:
        return None
    
    # Clean: normalize whitespace and remove extra spaces
    cleaned = re.sub(r"\s+", " ", original)
    
    # Extract alphanumeric only (for exact matching)
    alphanumeric = re.sub(r"[^A-Za-z0-9]", "", cleaned)
    
    # Tokenize: split by common delimiters
    tokens = re.split(r"[/\-_\s,;:|]+", cleaned)
    
    # Filter tokens: keep only meaningful ones (length >= 3, alphanumeric)
    meaningful_tokens = [
        token.upper() for token in tokens
        if len(token) >= 3 and re.match(r"^[A-Za-z0-9]+$", token)
    ]
    
    return NormalizedReference(
        original=original,
        cleaned=cleaned.upper(),
        tokens=meaningful_tokens,
        alphanumeric_only=alphanumeric.upper(),
    )


# ============================================================================
# Bank Enrichment
# ============================================================================

def enrich_bank_info(
    sender_email: str | None = None,
    sender_name: str | None = None,
    subject: str | None = None,
) -> EnrichmentMetadata:
    """
    Enrich transaction with bank information.
    
    Maps sender email/name to known bank codes and names.
    
    Args:
        sender_email: Sender email address
        sender_name: Sender name from parsed data
        subject: Email subject (for additional context)
        
    Returns:
        EnrichmentMetadata with bank information
    """
    enrichment = EnrichmentMetadata()
    
    # Check sender email domain
    if sender_email:
        sender_email_lower = sender_email.lower()
        for bank_key, bank_info in BANK_MAPPINGS.items():
            for domain in bank_info["domains"]:
                if domain in sender_email_lower:
                    enrichment.bank_code = bank_info["code"]
                    enrichment.bank_name = bank_info["name"]
                    enrichment.enrichment_confidence = 0.95
                    return enrichment
    
    # Check sender name
    if sender_name:
        sender_name_lower = sender_name.lower()
        # Remove common words that interfere with matching
        sender_name_clean = sender_name_lower.replace(" ", "").replace("-", "")
        for bank_key, bank_info in BANK_MAPPINGS.items():
            bank_key_clean = bank_key.replace(" ", "").replace("-", "")
            code_clean = bank_info["code"].lower().replace(" ", "").replace("-", "")
            if bank_key_clean in sender_name_clean or code_clean in sender_name_clean:
                enrichment.bank_code = bank_info["code"]
                enrichment.bank_name = bank_info["name"]
                enrichment.enrichment_confidence = 0.85
                return enrichment
    
    # Check subject
    if subject:
        subject_lower = subject.lower()
        for bank_key, bank_info in BANK_MAPPINGS.items():
            if bank_key in subject_lower or bank_info["code"].lower() in subject_lower:
                enrichment.bank_code = bank_info["code"]
                enrichment.bank_name = bank_info["name"]
                enrichment.enrichment_confidence = 0.75
                return enrichment
    
    return enrichment


# ============================================================================
# Composite Key Generation
# ============================================================================

def create_composite_key(
    amount: Decimal | None,
    currency: str | None,
    timestamp: datetime | None,
    reference: NormalizedReference | None,
    account_number: str | None = None,
    time_window_hours: int = 24,
) -> CompositeKey | None:
    """
    Create composite key for transaction matching.
    
    Key components:
    - Amount (normalized string)
    - Currency code
    - Date bucket (time window)
    - Top 3 reference tokens
    - Last 4 digits of account (if available)
    
    Args:
        amount: Normalized amount
        currency: ISO currency code
        timestamp: Normalized timestamp
        reference: Normalized reference
        account_number: Account number
        time_window_hours: Time window in hours for date bucketing
        
    Returns:
        CompositeKey or None if required fields missing
    """
    if amount is None or currency is None or timestamp is None:
        logger.debug("Cannot create composite key: missing required fields")
        return None
    
    # Amount as string (2 decimal places)
    amount_str = f"{amount:.2f}"
    
    # Date bucket: YYYY-MM-DD-HH (rounded to time window)
    bucket_hour = (timestamp.hour // time_window_hours) * time_window_hours
    date_bucket = timestamp.strftime("%Y-%m-%d") + f"-{bucket_hour:02d}"
    
    # Reference tokens (top 3)
    reference_tokens = reference.tokens[:3] if reference else []
    
    # Account last 4 digits
    account_last4 = None
    if account_number:
        # Extract digits only
        digits = re.sub(r"\D", "", account_number)
        if len(digits) >= 4:
            account_last4 = digits[-4:]
    
    return CompositeKey(
        amount_str=amount_str,
        currency=currency,
        date_bucket=date_bucket,
        reference_tokens=reference_tokens,
        account_last4=account_last4,
    )


# ============================================================================
# Main Normalization Functions
# ============================================================================

def normalize_email(parsed_email: ParsedEmail) -> NormalizedEmail:
    """
    Normalize and enrich a parsed email.
    
    Args:
        parsed_email: ParsedEmail from parser
        
    Returns:
        NormalizedEmail with normalized and enriched data
    """
    # Normalize amount and currency
    normalized_amount = normalize_amount(parsed_email.amount)
    normalized_currency = normalize_currency(parsed_email.currency)
    
    # Normalize timestamp
    normalized_timestamp = normalize_timestamp(parsed_email.email_timestamp)
    normalized_received_at = normalize_timestamp(parsed_email.received_at)
    
    # Normalize reference
    normalized_ref = normalize_reference(parsed_email.reference)
    
    # Enrich bank info
    enrichment = enrich_bank_info(
        sender_email=parsed_email.sender,
        sender_name=parsed_email.sender_name,
        subject=parsed_email.subject,
    )
    
    # Create composite key
    composite_key = create_composite_key(
        amount=normalized_amount,
        currency=normalized_currency,
        timestamp=normalized_timestamp,
        reference=normalized_ref,
        account_number=parsed_email.account_number,
    )
    
    # Calculate normalization quality
    quality_score = 0.0
    quality_count = 0
    
    if normalized_amount is not None:
        quality_score += 0.25
        quality_count += 1
    if normalized_currency is not None:
        quality_score += 0.15
        quality_count += 1
    if normalized_timestamp is not None:
        quality_score += 0.20
        quality_count += 1
    if normalized_ref is not None:
        quality_score += 0.20
        quality_count += 1
    if enrichment.bank_code is not None:
        quality_score += enrichment.enrichment_confidence * 0.20
        quality_count += 1
    
    normalization_quality = quality_score if quality_count > 0 else 0.0
    
    return NormalizedEmail(
        message_id=parsed_email.message_id,
        sender=parsed_email.sender,
        subject=parsed_email.subject,
        body=parsed_email.body,
        amount=normalized_amount,
        currency=normalized_currency,
        transaction_type=parsed_email.transaction_type,
        sender_name=parsed_email.sender_name,
        recipient_name=parsed_email.recipient_name,
        account_number=parsed_email.account_number,
        reference=normalized_ref,
        timestamp=normalized_timestamp,
        received_at=normalized_received_at or datetime.now(timezone.utc),
        enrichment=enrichment,
        composite_key=composite_key,
        parsed_at=parsed_email.parsed_at,
        parsing_method=parsed_email.parsing_method,
        parsing_confidence=parsed_email.confidence,
        normalization_quality=normalization_quality,
    )


def normalize_transaction(
    transaction_id: str,
    external_source: str,
    amount: Decimal | float | str,
    currency: str,
    timestamp: datetime | str,
    reference: str | None = None,
    account_ref: str | None = None,
    transaction_type: str | None = None,
    description: str | None = None,
) -> NormalizedTransaction:
    """
    Normalize and enrich a transaction.
    
    Args:
        transaction_id: Unique transaction ID
        external_source: Source system
        amount: Transaction amount
        currency: Currency code
        timestamp: Transaction timestamp
        reference: Transaction reference
        account_ref: Account reference
        transaction_type: Transaction type
        description: Transaction description
        
    Returns:
        NormalizedTransaction with normalized data
    """
    # Normalize amount and currency
    normalized_amount = normalize_amount(amount)
    if normalized_amount is None:
        normalized_amount = Decimal("0.00")
    
    normalized_currency = normalize_currency(currency)
    if normalized_currency is None:
        normalized_currency = "NGN"
    
    # Normalize timestamp
    normalized_timestamp = normalize_timestamp(timestamp)
    if normalized_timestamp is None:
        normalized_timestamp = datetime.now(timezone.utc)
    
    # Normalize reference
    normalized_ref = normalize_reference(reference)
    
    # Extract account last 4 digits
    account_last4 = None
    if account_ref:
        digits = re.sub(r"\D", "", account_ref)
        if len(digits) >= 4:
            account_last4 = digits[-4:]
    
    # Enrich bank info (from description or reference)
    enrichment = enrich_bank_info(
        sender_name=description,
        subject=reference,
    )
    
    # Create composite key
    composite_key = create_composite_key(
        amount=normalized_amount,
        currency=normalized_currency,
        timestamp=normalized_timestamp,
        reference=normalized_ref,
        account_number=account_ref,
    )
    
    # Calculate normalization quality
    quality_score = 1.0  # Transactions are generally well-structured
    
    return NormalizedTransaction(
        transaction_id=transaction_id,
        external_source=external_source,
        amount=normalized_amount,
        currency=normalized_currency,
        transaction_type=transaction_type,
        reference=normalized_ref,
        account_ref=account_ref,
        account_last4=account_last4,
        timestamp=normalized_timestamp,
        enrichment=enrichment,
        composite_key=composite_key,
        normalization_quality=quality_score,
        description=description,
    )
