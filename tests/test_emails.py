"""Tests for email fetcher and parser module."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.emails.config import EmailConfig, FilterConfig, LLMConfig, ParserConfig
from app.emails.filter import RuleBasedFilter
from app.emails.models import RawEmail
from app.emails.regex_extractor import RegexExtractor


class TestRuleBasedFilter:
    """Tests for rule-based email filtering."""

    @pytest.fixture
    def filter_config(self):
        """Create filter configuration."""
        return FilterConfig()

    @pytest.fixture
    def filter(self, filter_config):
        """Create filter instance."""
        return RuleBasedFilter(filter_config)

    def test_filter_passes_valid_alert(self, filter):
        """Test that valid bank alert passes filter."""
        email = RawEmail(
            message_id="test-001",
            sender="alerts@gtbank.com",
            subject="Transaction ALERT: Credit",
            body_plain="Your account has been credited with NGN 10,000.00 from sender John Doe on 04/11/2025",
            received_at=datetime.now(timezone.utc),
        )

        result = filter.filter_email(email)

        assert result.passed is True
        assert result.matched_whitelist is True
        assert len(result.matched_keywords) > 0

    def test_filter_rejects_non_whitelisted_sender(self, filter):
        """Test that non-whitelisted sender is rejected."""
        email = RawEmail(
            message_id="test-002",
            sender="spam@unknown.com",
            subject="Credit Alert",
            body_plain="You won a prize!",
            received_at=datetime.now(timezone.utc),
        )

        result = filter.filter_email(email)

        assert result.passed is False
        assert result.matched_whitelist is False
        assert "whitelist" in result.reason.lower()

    def test_filter_rejects_blacklisted_patterns(self, filter):
        """Test that blacklisted patterns are rejected."""
        email = RawEmail(
            message_id="test-003",
            sender="alerts@gtbank.com",
            subject="Your Monthly Statement is Ready",
            body_plain="Download your statement here",
            received_at=datetime.now(timezone.utc),
        )

        result = filter.filter_email(email)

        assert result.passed is False
        assert len(result.matched_blacklist) > 0
        assert "statement" in result.matched_blacklist[0].lower()

    def test_filter_rejects_missing_keywords(self, filter):
        """Test that emails without alert keywords are rejected."""
        email = RawEmail(
            message_id="test-004",
            sender="alerts@gtbank.com",
            subject="Welcome to Online Banking",
            body_plain="Thank you for registering with our online banking platform",
            received_at=datetime.now(timezone.utc),
        )

        result = filter.filter_email(email)

        assert result.passed is False
        assert "keyword" in result.reason.lower()

    def test_filter_rejects_short_body(self, filter):
        """Test that emails with too short body are rejected."""
        email = RawEmail(
            message_id="test-005",
            sender="alerts@gtbank.com",
            subject="Transaction Alert",
            body_plain="OK",
            received_at=datetime.now(timezone.utc),
        )

        result = filter.filter_email(email)

        assert result.passed is False
        assert "short" in result.reason.lower()


class TestRegexExtractor:
    """Tests for regex-based extraction."""

    @pytest.fixture
    def extractor(self):
        """Create extractor instance."""
        return RegexExtractor()

    def test_extract_amount_with_currency_symbol(self, extractor):
        """Test extraction of amount with NGN symbol."""
        text = "Your account has been credited with NGN 25,000.00"
        result = extractor.extract_fields("Alert", text)

        assert result.amount == Decimal("25000.00")
        assert result.currency == "NGN"

    def test_extract_amount_with_naira_symbol(self, extractor):
        """Test extraction of amount with ₦ symbol."""
        text = "Amount: ₦10,500.50 has been debited"
        result = extractor.extract_fields("Alert", text)

        assert result.amount == Decimal("10500.50")
        assert result.currency == "NGN"

    def test_determine_credit_transaction(self, extractor):
        """Test identification of credit transaction."""
        text = "Your account has been credited with NGN 5,000"
        result = extractor.extract_fields("Credit Alert", text)

        assert result.transaction_type == "credit"

    def test_determine_debit_transaction(self, extractor):
        """Test identification of debit transaction."""
        text = "Your account has been debited with NGN 5,000"
        result = extractor.extract_fields("Debit Alert", text)

        assert result.transaction_type == "debit"

    def test_extract_reference_number(self, extractor):
        """Test extraction of reference number."""
        text = "Transaction Reference: FBN/TRF/123456789"
        result = extractor.extract_fields("Alert", text)

        assert result.reference == "FBN/TRF/123456789"

    def test_extract_account_number(self, extractor):
        """Test extraction of account number."""
        text = "Account: 0123456789 has been credited"
        result = extractor.extract_fields("Alert", text)

        assert result.account_number == "0123456789"

    def test_extract_datetime(self, extractor):
        """Test extraction of timestamp."""
        text = "Transaction Date: 04/11/2025 14:30:00"
        result = extractor.extract_fields("Alert", text)

        assert result.timestamp is not None
        assert result.timestamp.day == 4
        assert result.timestamp.month == 11

    def test_gtbank_format(self, extractor):
        """Test extraction from GTBank format."""
        subject = "Debit Transaction Notification"
        body = """
GTBank Transaction Alert

Acct: 0123456789
Date: 04-11-2025 14:30
Desc: POS Purchase
Amt: NGN 5,500.00
Ref: GTB/POS/987654321
        """

        result = extractor.extract_fields(subject, body)

        assert result.amount == Decimal("5500.00")
        assert result.currency == "NGN"
        assert result.transaction_type == "debit"
        assert result.reference == "GTB/POS/987654321"
        assert result.fields_extracted >= 3

    def test_firstbank_format(self, extractor):
        """Test extraction from FirstBank format."""
        subject = "Transaction Alert: Credit"
        body = """
Your account has been credited with NGN 25,000.00.

Reference: FBN/TRF/123456789
Date: 04/11/2025 10:15:00
Account: ****5678
Sender: John Doe
        """

        result = extractor.extract_fields(subject, body)

        assert result.amount == Decimal("25000.00")
        assert result.currency == "NGN"
        assert result.transaction_type == "credit"
        assert result.reference == "FBN/TRF/123456789"
        assert result.fields_extracted >= 4


class TestParserConfig:
    """Tests for parser configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ParserConfig()

        assert config.min_confidence_threshold == 0.7
        assert config.fallback_to_regex is True
        assert config.require_amount is True

    def test_email_config_from_settings(self):
        """Test creating EmailConfig from settings."""

        class MockSettings:
            GROQ_API_KEY = "test-key"
            GROQ_MODEL = "llama-3.1-8b-instant"

        settings = MockSettings()
        config = EmailConfig.from_settings(settings)

        assert config.llm.enabled is True
        assert config.llm.api_key == "test-key"
        assert config.llm.model == "llama-3.1-8b-instant"


@pytest.mark.asyncio
class TestHybridParser:
    """Tests for hybrid parser (integration tests)."""

    async def test_parser_filters_out_non_alert(self):
        """Test that parser filters out non-alert emails."""
        from app.emails.parser import HybridParser

        config = EmailConfig(
            llm=LLMConfig(enabled=False),  # Disable LLM for this test
        )
        parser = HybridParser(config)

        email = RawEmail(
            message_id="test-non-alert",
            sender="alerts@gtbank.com",
            subject="Your Monthly Statement",
            body_plain="Your statement is ready for download",
            received_at=datetime.now(timezone.utc),
        )

        result = await parser.parse_email(email)

        # Should be filtered out
        assert result is None

    async def test_parser_processes_valid_alert_with_regex(self):
        """Test that parser processes valid alert using regex."""
        from app.emails.parser import HybridParser

        config = EmailConfig(
            llm=LLMConfig(enabled=False),  # Disable LLM, use regex only
        )
        parser = HybridParser(config)

        email = RawEmail(
            message_id="test-valid-alert",
            sender="alerts@gtbank.com",
            subject="Transaction ALERT: Credit",
            body_plain="""
Your account has been credited with NGN 15,000.00

Reference: GTB/TRF/ABC123
Date: 04/11/2025 10:00:00
Account: 0123456789
            """,
            received_at=datetime.now(timezone.utc),
        )

        result = await parser.parse_email(email)

        assert result is not None
        assert result.is_alert is True
        assert result.amount == Decimal("15000.00")
        assert result.currency == "NGN"
        assert result.reference == "GTB/TRF/ABC123"
        assert result.parsing_method == "regex"
        assert result.confidence > 0.3


class TestEmailMetrics:
    """Tests for email metrics tracking."""

    def test_metrics_tracking(self):
        """Test metrics tracking through a run."""
        from app.emails.metrics import ParserMetrics

        metrics = ParserMetrics()

        # Start run
        metrics.start_run("test-run-001")

        # Record events
        metrics.record_fetch(10)
        metrics.record_filtered()
        metrics.record_filtered()

        metrics.record_classified(is_alert=True)
        metrics.record_parsed(
            parsing_method="regex",
            confidence=0.85,
            fields={"amount": 1000, "currency": "NGN", "reference": "REF123"},
        )
        metrics.record_stored()

        # End run
        metrics.end_run("SUCCESS")

        # Check metrics
        last_run = metrics.get_last_run()
        assert last_run is not None
        assert last_run.status == "SUCCESS"
        assert last_run.emails_fetched == 10
        assert last_run.emails_filtered == 2
        assert last_run.emails_parsed == 1
        assert last_run.emails_stored == 1
        assert last_run.avg_confidence == 0.85

    def test_aggregate_metrics(self):
        """Test aggregate metrics calculation."""
        from app.emails.metrics import ParserMetrics

        metrics = ParserMetrics()

        # Run 1
        metrics.start_run("run-001")
        metrics.record_fetch(5)
        metrics.record_parsed("regex", 0.8, {})
        metrics.record_stored()
        metrics.end_run("SUCCESS")

        # Run 2
        metrics.start_run("run-002")
        metrics.record_fetch(3)
        metrics.record_parsed("llm", 0.9, {})
        metrics.record_stored()
        metrics.end_run("SUCCESS")

        # Check aggregates
        agg = metrics.get_aggregate_metrics()
        assert agg["total_runs"] == 2
        assert agg["successful_runs"] == 2
        assert agg["total_emails_fetched"] == 8
        assert agg["total_emails_stored"] == 2
        assert agg["success_rate"] == 100.0
