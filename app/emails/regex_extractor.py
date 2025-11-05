"""Regex-based extraction for Nigerian bank alerts."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.emails.models import RegexExtractionResult

logger = logging.getLogger(__name__)


class RegexExtractor:
    """Regex-based extractor for bank alert emails."""

    # Amount patterns
    AMOUNT_PATTERNS = [
        r"(?:NGN|₦|N)\s*([\d,]+(?:\.\d{2})?)",  # NGN 1,000.00 or ₦1,000.00
        r"([\d,]+(?:\.\d{2})?)\s*(?:NGN|₦)",  # 1,000.00 NGN
        r"Amount[:\s]+([\d,]+(?:\.\d{2})?)",  # Amount: 1,000.00
        r"(?:Amt|AMT)[:\s]+([\d,]+(?:\.\d{2})?)",  # Amt: 1,000.00
    ]

    # Currency patterns
    CURRENCY_PATTERNS = [
        r"(NGN|USD|GBP|EUR)",
        r"(₦|N\s)",
    ]

    # Reference patterns
    REFERENCE_PATTERNS = [
        r"(?:Ref|Reference|REF)[:\s]+([A-Z0-9/]+)",
        r"(?:Txn|Transaction|TXN)[:\s]+([A-Z0-9/]+)",
        r"(?:FT|TRANSFER)[/\s]+([A-Z0-9/]+)",
    ]

    # Account number patterns
    ACCOUNT_PATTERNS = [
        r"(?:A/C|Account|Acct)[:\s]+(\d{10})",
        r"(?:to|from)\s+(\d{10})",
    ]

    # Sender/recipient patterns
    NAME_PATTERNS = [
        r"(?:from|FROM)\s+([A-Z][A-Za-z\s]+?)(?:\s+(?:to|on|at|A/C))",
        r"(?:to|TO)\s+([A-Z][A-Za-z\s]+?)(?:\s+(?:on|at|A/C))",
        r"Sender[:\s]+([A-Za-z\s]+)",
    ]

    # Date/time patterns
    DATETIME_PATTERNS = [
        r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})",  # 04/11/2025 10:30:00
        r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2})",  # 04-11-2025 10:30
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",  # 2025-11-04 10:30:00
    ]

    def extract_fields(self, subject: str, body: str) -> RegexExtractionResult:
        """Extract fields using regex patterns.

        Args:
            subject: Email subject
            body: Email body

        Returns:
            Extraction result
        """
        text = f"{subject}\n{body}"
        patterns_matched: dict[str, str] = {}

        # Extract amount
        amount = self._extract_amount(text, patterns_matched)

        # Extract currency
        currency = self._extract_currency(text, patterns_matched)

        # Determine transaction type from subject/body
        transaction_type = self._determine_transaction_type(
            subject, body, patterns_matched
        )

        # Extract reference
        reference = self._extract_reference(text, patterns_matched)

        # Extract account number
        account_number = self._extract_account(text, patterns_matched)

        # Extract sender name
        sender_name = self._extract_sender(text, patterns_matched)

        # Extract timestamp
        timestamp = self._extract_timestamp(text, patterns_matched)

        # Count extracted fields
        fields_extracted = sum(
            [
                amount is not None,
                currency is not None,
                transaction_type != "unknown",
                sender_name is not None,
                reference is not None,
                timestamp is not None,
            ]
        )

        # Calculate confidence
        confidence = min(0.3 + (fields_extracted * 0.08), 0.7)

        return RegexExtractionResult(
            amount=amount,
            currency=currency,
            transaction_type=transaction_type,
            sender_name=sender_name,
            reference=reference,
            account_number=account_number,
            timestamp=timestamp,
            confidence=confidence,
            fields_extracted=fields_extracted,
            patterns_matched=patterns_matched,
        )

    def _extract_amount(self, text: str, patterns_matched: dict) -> Decimal | None:
        """Extract amount from text."""
        for pattern in self.AMOUNT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(",", "")
                try:
                    patterns_matched["amount"] = pattern
                    return Decimal(amount_str)
                except Exception:
                    continue
        return None

    def _extract_currency(self, text: str, patterns_matched: dict) -> str | None:
        """Extract currency from text."""
        for pattern in self.CURRENCY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                currency = match.group(1).strip()
                if currency in ["₦", "N"]:
                    currency = "NGN"
                patterns_matched["currency"] = pattern
                return currency.upper()
        return None

    def _determine_transaction_type(
        self, subject: str, body: str, patterns_matched: dict
    ) -> Literal["credit", "debit", "unknown"]:
        """Determine transaction type from text."""
        text = f"{subject} {body}".lower()

        credit_keywords = ["credit", "credited", "received", "deposit", "incoming"]
        debit_keywords = ["debit", "debited", "withdrawal", "paid", "sent", "outgoing"]

        has_credit = any(keyword in text for keyword in credit_keywords)
        has_debit = any(keyword in text for keyword in debit_keywords)

        if has_credit and not has_debit:
            patterns_matched["transaction_type"] = "credit_keywords"
            return "credit"
        elif has_debit and not has_credit:
            patterns_matched["transaction_type"] = "debit_keywords"
            return "debit"
        else:
            return "unknown"

    def _extract_reference(self, text: str, patterns_matched: dict) -> str | None:
        """Extract reference number from text."""
        for pattern in self.REFERENCE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                patterns_matched["reference"] = pattern
                return match.group(1)
        return None

    def _extract_account(self, text: str, patterns_matched: dict) -> str | None:
        """Extract account number from text."""
        for pattern in self.ACCOUNT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                patterns_matched["account"] = pattern
                return match.group(1)
        return None

    def _extract_sender(self, text: str, patterns_matched: dict) -> str | None:
        """Extract sender name from text."""
        for pattern in self.NAME_PATTERNS:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                if len(name) > 3:  # Sanity check
                    patterns_matched["sender"] = pattern
                    return name
        return None

    def _extract_timestamp(self, text: str, patterns_matched: dict) -> datetime | None:
        """Extract timestamp from text."""
        for pattern in self.DATETIME_PATTERNS:
            match = re.search(pattern, text)
            if match:
                timestamp_str = match.group(1)
                try:
                    # Try multiple formats
                    for fmt in [
                        "%d/%m/%Y %H:%M:%S",
                        "%d-%m-%Y %H:%M",
                        "%Y-%m-%d %H:%M:%S",
                    ]:
                        try:
                            patterns_matched["timestamp"] = pattern
                            return datetime.strptime(timestamp_str, fmt)
                        except ValueError:
                            continue
                except Exception:
                    continue
        return None
