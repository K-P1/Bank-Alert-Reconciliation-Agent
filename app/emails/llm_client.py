"""LLM client for email classification and extraction using Groq API."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

import httpx

from app.emails.models import LLMClassificationResult, LLMExtractionResult

if TYPE_CHECKING:
    from app.emails.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for LLM-assisted email parsing using Groq API."""

    GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, config: LLMConfig):
        """Initialize LLM client.

        Args:
            config: LLM configuration
        """
        self.config = config
        if not self.config.api_key:
            raise ValueError("GROQ_API_KEY is required")

    async def classify_email(self, subject: str, body: str) -> LLMClassificationResult:
        """Classify if email is a transaction alert.

        Args:
            subject: Email subject
            body: Email body

        Returns:
            Classification result
        """
        prompt = self._build_classification_prompt(subject, body)

        try:
            response = await self._call_llm(
                prompt=prompt,
                temperature=self.config.classification_temperature,
                max_tokens=self.config.classification_max_tokens,
            )

            # Parse response
            is_alert, confidence = self._parse_classification_response(response)

            return LLMClassificationResult(
                is_alert=is_alert,
                confidence=confidence,
                raw_response=response,
            )

        except Exception as e:
            logger.error(f"Error during LLM classification: {e}")
            return LLMClassificationResult(
                is_alert=False,
                confidence=0.0,
                raw_response=str(e),
            )

    async def extract_fields(self, subject: str, body: str) -> LLMExtractionResult:
        """Extract transaction fields from email.

        Args:
            subject: Email subject
            body: Email body

        Returns:
            Extraction result
        """
        prompt = self._build_extraction_prompt(subject, body)

        try:
            response = await self._call_llm(
                prompt=prompt,
                temperature=self.config.extraction_temperature,
                max_tokens=self.config.extraction_max_tokens,
            )

            # Parse JSON response
            extracted_data = self._parse_extraction_response(response)

            return extracted_data

        except Exception as e:
            logger.error(f"Error during LLM extraction: {e}")
            return LLMExtractionResult(
                confidence=0.0,
                fields_extracted=0,
                raw_response=str(e),
            )

    async def _call_llm(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """Call Groq API.

        Args:
            prompt: Prompt text
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Response text
        """
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            for attempt in range(self.config.max_retries + 1):
                try:
                    response = await client.post(
                        self.GROQ_API_URL,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()

                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    return content.strip()

                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error from Groq API (attempt {attempt + 1}): {e}")
                    if attempt == self.config.max_retries:
                        raise
                except Exception as e:
                    logger.error(f"Error calling Groq API (attempt {attempt + 1}): {e}")
                    if attempt == self.config.max_retries:
                        raise

        raise RuntimeError("Failed to call LLM after all retries")

    def _build_classification_prompt(self, subject: str, body: str) -> str:
        """Build prompt for classification.

        Args:
            subject: Email subject
            body: Email body

        Returns:
            Prompt string
        """
        # Truncate body if too long
        body = body[:1000] if len(body) > 1000 else body

        return f"""Determine if the following email is a transaction alert (e.g., credit or debit notification from a bank).
Reply ONLY with "YES" or "NO".

Subject: {subject}
Body: {body}"""

    def _build_extraction_prompt(self, subject: str, body: str) -> str:
        """Build prompt for extraction.

        Args:
            subject: Email subject
            body: Email body

        Returns:
            Prompt string
        """
        # Truncate body if too long
        body = body[:2000] if len(body) > 2000 else body

        return f"""Extract transaction details from this bank alert email.
Return ONLY a JSON object with these fields (use null if not found):
- amount (number, no currency symbols or commas)
- currency (3-letter code like NGN, USD)
- transaction_type (exactly one of: "credit", "debit", or "unknown")
- sender_name (name of person/entity sending money)
- recipient_name (name of person/entity receiving money)
- reference (transaction reference number)
- account_number (account number mentioned)
- timestamp (ISO 8601 format like "2025-11-04T10:30:00Z")

Subject: {subject}
Body: {body}

JSON:"""

    def _parse_classification_response(self, response: str) -> tuple[bool, float]:
        """Parse classification response.

        Args:
            response: LLM response

        Returns:
            Tuple of (is_alert, confidence)
        """
        response_upper = response.upper().strip()

        if "YES" in response_upper:
            return True, 0.9
        elif "NO" in response_upper:
            return False, 0.9
        else:
            # Uncertain response
            logger.warning(f"Unexpected classification response: {response}")
            return False, 0.5

    def _parse_extraction_response(self, response: str) -> LLMExtractionResult:
        """Parse extraction response.

        Args:
            response: LLM response

        Returns:
            Extraction result
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in response")

            data = json.loads(json_match.group(0))

            # Extract fields
            amount = None
            if data.get("amount"):
                try:
                    amount = Decimal(str(data["amount"]))
                except Exception:
                    pass

            currency = data.get("currency")
            if currency:
                currency = currency.upper()

            transaction_type = data.get("transaction_type")
            if transaction_type and transaction_type.lower() in ["credit", "debit", "unknown"]:
                transaction_type = transaction_type.lower()
            else:
                transaction_type = "unknown"

            sender_name = data.get("sender_name")
            recipient_name = data.get("recipient_name")
            reference = data.get("reference")
            account_number = data.get("account_number")

            timestamp = None
            if data.get("timestamp"):
                try:
                    timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                except Exception:
                    pass

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

            # Calculate confidence based on fields extracted
            confidence = min(0.5 + (fields_extracted * 0.08), 0.98)

            return LLMExtractionResult(
                amount=amount,
                currency=currency,
                transaction_type=transaction_type,
                sender_name=sender_name,
                recipient_name=recipient_name,
                reference=reference,
                account_number=account_number,
                timestamp=timestamp,
                confidence=confidence,
                fields_extracted=fields_extracted,
                raw_response=response,
            )

        except Exception as e:
            logger.error(f"Error parsing extraction response: {e}")
            return LLMExtractionResult(
                confidence=0.0,
                fields_extracted=0,
                raw_response=response,
            )
