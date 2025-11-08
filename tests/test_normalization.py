"""Tests for normalization and enrichment functions."""

from datetime import datetime, timezone
from decimal import Decimal

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
from app.emails.models import ParsedEmail


class TestAmountNormalization:
    """Test amount normalization."""

    def test_normalize_amount_with_ngn_symbol(self):
        """Test Nigerian Naira symbol."""
        assert normalize_amount("₦23,500.00") == Decimal("23500.00")
        assert normalize_amount("₦1,000") == Decimal("1000.00")
        assert normalize_amount("₦500") == Decimal("500.00")

    def test_normalize_amount_with_currency_code(self):
        """Test currency codes."""
        assert normalize_amount("NGN 23,500.00") == Decimal("23500.00")
        assert normalize_amount("USD 1,234.56") == Decimal("1234.56")
        assert normalize_amount("23500 NGN") == Decimal("23500.00")

    def test_normalize_amount_plain_numbers(self):
        """Test plain numeric formats."""
        assert normalize_amount("23500") == Decimal("23500.00")
        assert normalize_amount("23500.50") == Decimal("23500.50")
        assert normalize_amount("1234.56") == Decimal("1234.56")

    def test_normalize_amount_with_commas(self):
        """Test thousand separators."""
        assert normalize_amount("1,000,000") == Decimal("1000000.00")
        assert normalize_amount("500,000.50") == Decimal("500000.50")

    def test_normalize_amount_numeric_types(self):
        """Test numeric input types."""
        assert normalize_amount(23500) == Decimal("23500.00")
        assert normalize_amount(23500.50) == Decimal("23500.50")
        assert normalize_amount(Decimal("23500.00")) == Decimal("23500.00")

    def test_normalize_amount_edge_cases(self):
        """Test edge cases."""
        assert normalize_amount(None) is None
        assert normalize_amount("") is None
        assert normalize_amount("invalid") is None
        assert normalize_amount("   ") is None


class TestCurrencyNormalization:
    """Test currency normalization."""

    def test_normalize_currency_symbols(self):
        """Test currency symbols."""
        assert normalize_currency("₦") == "NGN"
        assert normalize_currency("N") == "NGN"
        assert normalize_currency("$") == "USD"
        assert normalize_currency("£") == "GBP"
        assert normalize_currency("€") == "EUR"

    def test_normalize_currency_codes(self):
        """Test ISO codes."""
        assert normalize_currency("NGN") == "NGN"
        assert normalize_currency("USD") == "USD"
        assert normalize_currency("GBP") == "GBP"
        assert normalize_currency("eur") == "EUR"

    def test_normalize_currency_names(self):
        """Test currency names."""
        assert normalize_currency("naira") == "NGN"
        assert normalize_currency("NAIRA") == "NGN"
        assert normalize_currency("dollar") == "USD"
        assert normalize_currency("pounds") == "GBP"

    def test_normalize_currency_edge_cases(self):
        """Test edge cases."""
        assert normalize_currency(None) is None
        assert normalize_currency("unknown") == "NGN"  # Default
        assert normalize_currency("") == "NGN"  # Default


class TestTimestampNormalization:
    """Test timestamp normalization."""

    def test_normalize_timestamp_datetime_objects(self):
        """Test datetime objects."""
        # UTC datetime
        dt_utc = datetime(2025, 11, 4, 10, 30, 0, tzinfo=timezone.utc)
        result = normalize_timestamp(dt_utc)
        assert result is not None
        assert result == dt_utc
        assert result.tzinfo == timezone.utc

        # Naive datetime (should add UTC)
        dt_naive = datetime(2025, 11, 4, 10, 30, 0)
        result = normalize_timestamp(dt_naive)
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.hour == 10

    def test_normalize_timestamp_iso_strings(self):
        """Test ISO 8601 strings."""
        result = normalize_timestamp("2025-11-04T10:30:00Z")
        assert result is not None
        assert result.year == 2025
        assert result.month == 11
        assert result.day == 4
        assert result.hour == 10
        assert result.tzinfo == timezone.utc

    def test_normalize_timestamp_nigerian_formats(self):
        """Test common Nigerian date formats."""
        # DD/MM/YYYY HH:MM:SS
        result = normalize_timestamp("04/11/2025 10:30:00")
        assert result is not None
        assert result.year == 2025
        assert result.month == 11
        assert result.day == 4
        assert result.hour == 10

        # DD/MM/YYYY HH:MM
        result = normalize_timestamp("04/11/2025 10:30")
        assert result is not None
        assert result.year == 2025
        assert result.month == 11
        assert result.day == 4

        # DD-MM-YYYY HH:MM:SS
        result = normalize_timestamp("04-11-2025 10:30:00")
        assert result is not None
        assert result.year == 2025
        assert result.month == 11

    def test_normalize_timestamp_edge_cases(self):
        """Test edge cases."""
        assert normalize_timestamp(None) is None
        assert normalize_timestamp("") is None
        assert normalize_timestamp("invalid") is None


class TestReferenceNormalization:
    """Test reference string normalization."""

    def test_normalize_reference_basic(self):
        """Test basic reference normalization."""
        ref = normalize_reference("GTB/TRF/2025/001")
        assert ref is not None
        assert ref.original == "GTB/TRF/2025/001"
        assert ref.cleaned == "GTB/TRF/2025/001"
        assert "GTB" in ref.tokens
        assert "TRF" in ref.tokens
        assert "2025" in ref.tokens
        assert "001" in ref.tokens

    def test_normalize_reference_with_spaces(self):
        """Test reference with extra spaces."""
        ref = normalize_reference("  GTB  /  TRF  / 2025  ")
        assert ref is not None
        assert ref.cleaned == "GTB / TRF / 2025"
        assert "GTB" in ref.tokens

    def test_normalize_reference_alphanumeric(self):
        """Test alphanumeric extraction."""
        ref = normalize_reference("GTB/TRF-2025_001")
        assert ref is not None
        assert ref.alphanumeric_only == "GTBTRF2025001"

    def test_normalize_reference_tokens(self):
        """Test token extraction."""
        ref = normalize_reference("FBN-TRANSFER-2025-ABC123")
        assert ref is not None
        assert "FBN" in ref.tokens
        assert "TRANSFER" in ref.tokens
        assert "2025" in ref.tokens
        assert "ABC123" in ref.tokens

    def test_normalize_reference_short_tokens_filtered(self):
        """Test short tokens are filtered out."""
        ref = normalize_reference("GTB/A/B/TRANSFER")
        assert ref is not None
        # "A" and "B" should be filtered (length < 3)
        assert "A" not in ref.tokens
        assert "B" not in ref.tokens
        assert "GTB" in ref.tokens
        assert "TRANSFER" in ref.tokens

    def test_normalize_reference_edge_cases(self):
        """Test edge cases."""
        assert normalize_reference(None) is None
        assert normalize_reference("") is None
        assert normalize_reference("   ") is None


class TestBankEnrichment:
    """Test bank information enrichment."""

    def test_enrich_bank_from_email_domain(self):
        """Test enrichment from email domain."""
        enrichment = enrich_bank_info(sender_email="alerts@gtbank.com")
        assert enrichment.bank_code == "GTB"
        # Accept official registered name with or without 'Plc' suffix
        assert enrichment.bank_name in {"Guaranty Trust Bank", "Guaranty Trust Bank Plc"}
        assert enrichment.enrichment_confidence == 0.95

        enrichment = enrich_bank_info(sender_email="notifications@accessbankplc.com")
        assert enrichment.bank_code == "ACC"
        assert enrichment.bank_name == "Access Bank Plc"

    def test_enrich_bank_from_sender_name(self):
        """Test enrichment from sender name."""
        enrichment = enrich_bank_info(sender_name="GTBank Alerts")
        assert enrichment.bank_code == "GTB"
        # Accept official registered name with or without 'Plc'
        assert enrichment.bank_name in {"Guaranty Trust Bank", "Guaranty Trust Bank Plc"}
        assert enrichment.enrichment_confidence == 0.85

        enrichment = enrich_bank_info(sender_name="First Bank Nigeria")
        assert enrichment.bank_code == "FBN"

    def test_enrich_bank_from_subject(self):
        """Test enrichment from subject."""
        enrichment = enrich_bank_info(subject="Zenith Bank Transaction Alert")
        assert enrichment.bank_code == "ZEN"
        assert enrichment.bank_name == "Zenith Bank Plc"
        assert enrichment.enrichment_confidence == 0.75

    def test_enrich_bank_priority(self):
        """Test that email has priority over name over subject."""
        # Email should win
        enrichment = enrich_bank_info(
            sender_email="alerts@gtbank.com",
            sender_name="First Bank",
            subject="Zenith Bank",
        )
        assert enrichment.bank_code == "GTB"

    def test_enrich_bank_no_match(self):
        """Test when no bank matches."""
        enrichment = enrich_bank_info(
            sender_email="test@example.com",
            sender_name="Unknown Bank",
            subject="Transaction",
        )
        assert enrichment.bank_code is None
        assert enrichment.bank_name is None


class TestCompositeKeyGeneration:
    """Test composite key generation."""

    def test_create_composite_key_basic(self):
        """Test basic composite key creation."""
        ref = normalize_reference("GTB/TRF/2025/001")
        key = create_composite_key(
            amount=Decimal("23500.00"),
            currency="NGN",
            timestamp=datetime(2025, 11, 4, 10, 30, 0, tzinfo=timezone.utc),
            reference=ref,
        )
        assert key is not None
        assert key.amount_str == "23500.00"
        assert key.currency == "NGN"
        assert key.date_bucket == "2025-11-04-00"
        assert len(key.reference_tokens) <= 3

    def test_create_composite_key_with_account(self):
        """Test composite key with account number."""
        ref = normalize_reference("GTB/TRF/001")
        key = create_composite_key(
            amount=Decimal("1000.00"),
            currency="NGN",
            timestamp=datetime(2025, 11, 4, 10, 30, 0, tzinfo=timezone.utc),
            reference=ref,
            account_number="1234567890",
        )
        assert key is not None
        assert key.account_last4 == "7890"

    def test_create_composite_key_time_bucketing(self):
        """Test time window bucketing."""
        ref = normalize_reference("TEST")

        # Same day, different hours in same bucket
        key1 = create_composite_key(
            amount=Decimal("1000.00"),
            currency="NGN",
            timestamp=datetime(2025, 11, 4, 10, 0, 0, tzinfo=timezone.utc),
            reference=ref,
        )
        key2 = create_composite_key(
            amount=Decimal("1000.00"),
            currency="NGN",
            timestamp=datetime(2025, 11, 4, 23, 59, 59, tzinfo=timezone.utc),
            reference=ref,
        )
        assert key1 is not None
        assert key2 is not None
        assert key1.date_bucket == "2025-11-04-00"
        assert key2.date_bucket == "2025-11-04-00"

    def test_create_composite_key_to_string(self):
        """Test composite key string representation."""
        ref = normalize_reference("GTB/TRF/2025")
        key = create_composite_key(
            amount=Decimal("1000.50"),
            currency="NGN",
            timestamp=datetime(2025, 11, 4, 10, 0, 0, tzinfo=timezone.utc),
            reference=ref,
            account_number="1234567890",
        )
        assert key is not None
        key_str = key.to_string()
        assert "1000.50" in key_str
        assert "NGN" in key_str
        assert "2025-11-04" in key_str
        assert "7890" in key_str

    def test_create_composite_key_missing_fields(self):
        """Test composite key with missing required fields."""
        ref = normalize_reference("TEST")

        # Missing amount
        key = create_composite_key(
            amount=None,
            currency="NGN",
            timestamp=datetime(2025, 11, 4, 10, 0, 0, tzinfo=timezone.utc),
            reference=ref,
        )
        assert key is None

        # Missing currency
        key = create_composite_key(
            amount=Decimal("1000.00"),
            currency=None,
            timestamp=datetime(2025, 11, 4, 10, 0, 0, tzinfo=timezone.utc),
            reference=ref,
        )
        assert key is None

        # Missing timestamp
        key = create_composite_key(
            amount=Decimal("1000.00"),
            currency="NGN",
            timestamp=None,
            reference=ref,
        )
        assert key is None


class TestNormalizeEmail:
    """Test email normalization."""

    def test_normalize_email_complete_data(self):
        """Test normalization with complete data."""
        parsed_email = ParsedEmail(
            message_id="test-001",
            sender="alerts@gtbank.com",
            subject="Transaction Alert",
            body="You received NGN 23,500.00",
            amount=Decimal("23500.00"),
            currency="NGN",
            transaction_type="credit",
            sender_name="John Doe",
            recipient_name="Jane Doe",
            reference="GTB/TRF/2025/001",
            account_number="1234567890",
            email_timestamp=datetime(2025, 11, 4, 10, 30, 0, tzinfo=timezone.utc),
            received_at=datetime(2025, 11, 4, 10, 31, 0, tzinfo=timezone.utc),
            parsing_method="llm",
            confidence=0.95,
            is_alert=True,
        )

        normalized = normalize_email(parsed_email)

        assert normalized.message_id == "test-001"
        assert normalized.amount == Decimal("23500.00")
        assert normalized.currency == "NGN"
        assert normalized.reference is not None
        assert normalized.reference.original == "GTB/TRF/2025/001"
        assert normalized.enrichment is not None
        assert normalized.enrichment.bank_code == "GTB"
        assert normalized.composite_key is not None
        assert normalized.normalization_quality > 0.8

    def test_normalize_email_partial_data(self):
        """Test normalization with partial data."""
        parsed_email = ParsedEmail(
            message_id="test-002",
            sender="unknown@example.com",
            subject="Alert",
            body="Transaction",
            amount=None,
            currency=None,
            transaction_type=None,
            reference=None,
            email_timestamp=None,
            received_at=datetime.now(timezone.utc),
            parsing_method="regex",
            confidence=0.5,
            is_alert=True,
        )

        normalized = normalize_email(parsed_email)

        assert normalized.message_id == "test-002"
        assert normalized.amount is None
        assert normalized.currency is None
        assert normalized.reference is None
        assert normalized.composite_key is None
        assert normalized.normalization_quality < 0.5


class TestNormalizeTransaction:
    """Test transaction normalization."""

    def test_normalize_transaction_complete_data(self):
        """Test transaction normalization with complete data."""
        normalized = normalize_transaction(
            transaction_id="TXN-001",
            external_source="paystack",
            amount="₦23,500.00",
            currency="NGN",
            timestamp="04/11/2025 10:30:00",
            reference="GTB/TRF/2025/001",
            account_ref="1234567890",
            transaction_type="credit",
            description="Payment received",
        )

        assert normalized.transaction_id == "TXN-001"
        assert normalized.external_source == "paystack"
        assert normalized.amount == Decimal("23500.00")
        assert normalized.currency == "NGN"
        assert normalized.reference is not None
        assert normalized.reference.original == "GTB/TRF/2025/001"
        assert normalized.account_ref == "1234567890"
        assert normalized.account_last4 == "7890"
        assert normalized.composite_key is not None
        assert normalized.normalization_quality == 1.0

    def test_normalize_transaction_minimal_data(self):
        """Test transaction normalization with minimal data."""
        normalized = normalize_transaction(
            transaction_id="TXN-002",
            external_source="manual",
            amount=1000,
            currency="NGN",
            timestamp=datetime.now(timezone.utc),
        )

        assert normalized.transaction_id == "TXN-002"
        assert normalized.amount == Decimal("1000.00")
        assert normalized.currency == "NGN"
        assert normalized.reference is None
        assert normalized.account_ref is None


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_various_amount_formats(self):
        """Test various amount formats."""
        test_cases = [
            ("₦1,234,567.89", Decimal("1234567.89")),
            ("NGN1234567.89", Decimal("1234567.89")),
            ("1,234,567.89 NGN", Decimal("1234567.89")),
            ("$1,234.56", Decimal("1234.56")),
            ("1234.56", Decimal("1234.56")),
            ("1234", Decimal("1234.00")),
        ]

        for input_val, expected in test_cases:
            result = normalize_amount(input_val)
            assert result == expected, f"Failed for input: {input_val}"

    def test_various_currency_formats(self):
        """Test various currency formats."""
        test_cases = [
            ("₦", "NGN"),
            ("NGN", "NGN"),
            ("naira", "NGN"),
            ("$", "USD"),
            ("USD", "USD"),
            ("dollar", "USD"),
        ]

        for input_val, expected in test_cases:
            result = normalize_currency(input_val)
            assert result == expected, f"Failed for input: {input_val}"

    def test_various_date_formats(self):
        """Test various date formats."""
        test_cases = [
            "04/11/2025 10:30:00",
            "04/11/2025 10:30",
            "04-11-2025 10:30:00",
            "2025-11-04 10:30:00",
            "04 Nov 2025 10:30:00",
            "2025-11-04T10:30:00Z",
        ]

        for date_str in test_cases:
            result = normalize_timestamp(date_str)
            assert result is not None, f"Failed to parse: {date_str}"
            assert result.tzinfo is not None
