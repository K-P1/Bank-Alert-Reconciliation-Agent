"""Hybrid parser combining rule-based filtering, LLM classification, and extraction."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from app.emails.filter import RuleBasedFilter
from app.emails.llm_client import LLMClient
from app.emails.models import ParsedEmail, RawEmail
from app.emails.regex_extractor import RegexExtractor

if TYPE_CHECKING:
    from app.emails.config import EmailConfig

logger = logging.getLogger(__name__)


class HybridParser:
    """Hybrid parser combining multiple parsing strategies."""

    def __init__(self, config: EmailConfig):
        """Initialize hybrid parser.

        Args:
            config: Email configuration
        """
        self.config = config
        self.filter = RuleBasedFilter(config.filter)
        self.regex_extractor = RegexExtractor()

        # Initialize LLM client if enabled
        self.llm_client: LLMClient | None = None
        if config.llm.enabled and config.llm.api_key:
            try:
                self.llm_client = LLMClient(config.llm)
                logger.info("LLM client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize LLM client: {e}")
                self.llm_client = None
        else:
            logger.info("LLM client disabled")

    async def parse_email(self, email: RawEmail) -> ParsedEmail | None:
        """Parse email using hybrid approach.

        Pipeline:
        1. Pre-filtering (rule-based)
        2. LLM classification (if enabled)
        3. LLM extraction (if enabled)
        4. Regex extraction (fallback or if LLM disabled)
        5. Confidence scoring

        Args:
            email: Raw email to parse

        Returns:
            ParsedEmail or None if filtered out
        """
        parsing_errors: list[str] = []

        # Step 1: Pre-filtering
        filter_result = self.filter.filter_email(email)
        if not filter_result.passed:
            logger.debug(f"Email filtered out: {filter_result.reason}")
            return None

        logger.info(f"Email passed pre-filter: {email.message_id}")

        # Get body text (prefer plain over HTML)
        body = email.body_plain or email.body_html or ""

        # Step 2: LLM Classification (if enabled)
        is_alert = True
        classification_confidence = 0.5

        if self.llm_client:
            try:
                classification_result = await self.llm_client.classify_email(
                    email.subject, body
                )
                is_alert = classification_result.is_alert
                classification_confidence = classification_result.confidence

                logger.info(
                    f"LLM classification: is_alert={is_alert}, "
                    f"confidence={classification_confidence:.2f}"
                )

                if not is_alert:
                    logger.info(f"LLM classified as non-alert: {email.message_id}")
                    # Still create parsed email but mark as not alert
                    return self._create_parsed_email(
                        email=email,
                        body=body,
                        is_alert=False,
                        parsing_method="llm",
                        confidence=classification_confidence,
                        parsing_errors=parsing_errors,
                    )

            except Exception as e:
                logger.error(f"LLM classification failed: {e}")
                parsing_errors.append(f"LLM classification error: {str(e)}")

        # Step 3: Extraction (LLM first, then regex fallback)
        from app.emails.models import LLMExtractionResult, RegexExtractionResult

        extraction_result: LLMExtractionResult | RegexExtractionResult | None = None
        parsing_method = "regex"

        # Try LLM extraction first
        if self.llm_client and is_alert:
            try:
                extraction_result = await self.llm_client.extract_fields(
                    email.subject, body
                )

                if extraction_result.fields_extracted >= 2:  # At least 2 fields
                    parsing_method = "llm"
                    logger.info(
                        f"LLM extraction successful: "
                        f"{extraction_result.fields_extracted} fields, "
                        f"confidence={extraction_result.confidence:.2f}"
                    )
                else:
                    logger.info("LLM extraction insufficient, falling back to regex")
                    extraction_result = None

            except Exception as e:
                logger.error(f"LLM extraction failed: {e}")
                parsing_errors.append(f"LLM extraction error: {str(e)}")

        # Fallback to regex if needed
        if extraction_result is None and self.config.parser.fallback_to_regex:
            try:
                extraction_result = self.regex_extractor.extract_fields(
                    email.subject, body
                )
                parsing_method = "regex" if parsing_method == "regex" else "hybrid"

                logger.info(
                    f"Regex extraction: "
                    f"{extraction_result.fields_extracted} fields, "
                    f"confidence={extraction_result.confidence:.2f}"
                )

            except Exception as e:
                logger.error(f"Regex extraction failed: {e}")
                parsing_errors.append(f"Regex extraction error: {str(e)}")

        # Check if required fields are present
        if extraction_result:
            if self.config.parser.require_amount and extraction_result.amount is None:
                parsing_errors.append("Required field 'amount' not extracted")

            if (
                self.config.parser.require_timestamp
                and extraction_result.timestamp is None
            ):
                parsing_errors.append("Required field 'timestamp' not extracted")

        # Calculate final confidence
        if extraction_result:
            if parsing_method == "llm":
                final_confidence = (
                    extraction_result.confidence
                    * self.config.parser.llm_confidence_weight
                    + classification_confidence
                    * (1 - self.config.parser.llm_confidence_weight)
                )
            elif parsing_method == "regex":
                final_confidence = (
                    extraction_result.confidence
                    * self.config.parser.regex_confidence_weight
                )
            else:  # hybrid
                final_confidence = (
                    extraction_result.confidence * 0.6 + classification_confidence * 0.4
                )
        else:
            final_confidence = classification_confidence * 0.3

        # Log low confidence cases
        if (
            self.config.parser.log_low_confidence
            and final_confidence < self.config.parser.min_confidence_threshold
        ):
            logger.warning(
                f"Low confidence parse: {email.message_id}, "
                f"confidence={final_confidence:.2f}, "
                f"method={parsing_method}"
            )

        # Create parsed email
        parsed_email = self._create_parsed_email(
            email=email,
            body=body,
            is_alert=is_alert,
            parsing_method=parsing_method,
            confidence=final_confidence,
            extraction_result=extraction_result,
            parsing_errors=parsing_errors,
        )

        return parsed_email

    def _create_parsed_email(
        self,
        email: RawEmail,
        body: str,
        is_alert: bool,
        parsing_method: str,
        confidence: float,
        extraction_result=None,
        parsing_errors: list[str] | None = None,
    ) -> ParsedEmail:
        """Create ParsedEmail from extraction results.

        Args:
            email: Original raw email
            body: Email body text
            is_alert: Whether this is an alert
            parsing_method: Method used
            confidence: Confidence score
            extraction_result: Extraction result (if any)
            parsing_errors: List of errors

        Returns:
            ParsedEmail
        """
        # Ensure parsing_method is a valid Literal type
        valid_method: Literal["regex", "llm", "hybrid"]
        if parsing_method in ("regex", "llm", "hybrid"):
            valid_method = parsing_method  # type: ignore
        else:
            valid_method = "regex"  # Default fallback

        parsed_email = ParsedEmail(
            message_id=email.message_id,
            sender=email.sender,
            subject=email.subject,
            body=body,
            received_at=email.received_at,
            parsed_at=datetime.now(timezone.utc),
            parsing_method=valid_method,
            confidence=confidence,
            is_alert=is_alert,
            parsing_errors=parsing_errors or [],
        )

        # Add extracted fields if available
        if extraction_result:
            parsed_email.amount = extraction_result.amount
            parsed_email.currency = extraction_result.currency
            parsed_email.transaction_type = extraction_result.transaction_type
            parsed_email.sender_name = extraction_result.sender_name
            parsed_email.reference = extraction_result.reference
            parsed_email.account_number = extraction_result.account_number
            parsed_email.email_timestamp = extraction_result.timestamp

            # Handle recipient_name if from LLM
            if hasattr(extraction_result, "recipient_name"):
                parsed_email.recipient_name = extraction_result.recipient_name

        return parsed_email
