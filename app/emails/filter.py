"""Rule-based email filtering."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.emails.models import FilterResult, RawEmail

if TYPE_CHECKING:
    from app.emails.config import FilterConfig

logger = logging.getLogger(__name__)


class RuleBasedFilter:
    """Rule-based email filter to quickly exclude non-alerts."""

    def __init__(self, config: FilterConfig):
        """Initialize filter.

        Args:
            config: Filter configuration
        """
        self.config = config

    def filter_email(self, email: RawEmail) -> FilterResult:
        """Filter email based on rules.

        Args:
            email: Raw email to filter

        Returns:
            FilterResult indicating if email passed filters
        """
        # Check sender whitelist
        sender_lower = email.sender.lower()
        matched_whitelist = any(domain.lower() in sender_lower for domain in self.config.sender_whitelist)

        if not matched_whitelist:
            return FilterResult(
                passed=False,
                reason=f"Sender not in whitelist: {email.sender}",
                matched_whitelist=False,
            )

        # Check blacklist patterns in subject
        matched_blacklist = []
        subject_lower = email.subject.lower()
        for pattern in self.config.blacklist_patterns:
            if pattern.lower() in subject_lower:
                matched_blacklist.append(pattern)

        if matched_blacklist:
            return FilterResult(
                passed=False,
                reason=f"Subject contains blacklisted pattern(s): {', '.join(matched_blacklist)}",
                matched_whitelist=True,
                matched_blacklist=matched_blacklist,
            )

        # Check subject keywords
        matched_keywords = []
        for keyword in self.config.subject_keywords:
            if keyword.lower() in subject_lower:
                matched_keywords.append(keyword)

        if not matched_keywords:
            return FilterResult(
                passed=False,
                reason=f"Subject does not contain any alert keywords: {email.subject}",
                matched_whitelist=True,
            )

        # Check body length
        body = email.body_plain or email.body_html or ""
        if len(body) < self.config.min_body_length:
            return FilterResult(
                passed=False,
                reason=f"Body too short: {len(body)} < {self.config.min_body_length}",
                matched_whitelist=True,
                matched_keywords=matched_keywords,
            )

        # Passed all filters
        logger.debug(
            f"Email passed filters - sender: {email.sender}, "
            f"keywords: {matched_keywords}, "
            f"body_length: {len(body)}"
        )

        return FilterResult(
            passed=True,
            matched_whitelist=True,
            matched_keywords=matched_keywords,
        )
