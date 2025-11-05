"""IMAP connector for fetching emails from mailbox."""

from __future__ import annotations

import email
import imaplib
import logging
from datetime import datetime
from email.header import decode_header
from typing import TYPE_CHECKING

from app.emails.models import RawEmail

if TYPE_CHECKING:
    from app.emails.config import FetcherConfig

logger = logging.getLogger(__name__)


class IMAPConnector:
    """IMAP connector for fetching emails."""

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        config: FetcherConfig,
    ):
        """Initialize IMAP connector.

        Args:
            host: IMAP server hostname
            user: IMAP username
            password: IMAP password
            config: Fetcher configuration
        """
        self.host = host
        self.user = user
        self.password = password
        self.config = config
        self._connection: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        """Connect to IMAP server."""
        try:
            logger.info(f"Connecting to IMAP server: {self.host}")
            self._connection = imaplib.IMAP4_SSL(
                self.host, timeout=self.config.imap_timeout
            )
            self._connection.login(self.user, self.password)
            logger.info("IMAP connection established")
        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {e}")
            raise

    def disconnect(self) -> None:
        """Disconnect from IMAP server."""
        if self._connection:
            try:
                self._connection.logout()
                logger.info("IMAP connection closed")
            except Exception as e:
                logger.warning(f"Error closing IMAP connection: {e}")
            finally:
                self._connection = None

    def __enter__(self) -> IMAPConnector:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()

    def fetch_unread_emails(self, limit: int | None = None) -> list[RawEmail]:
        """Fetch unread emails from inbox.

        Args:
            limit: Maximum number of emails to fetch (defaults to config.batch_size)

        Returns:
            List of raw emails
        """
        if not self._connection:
            raise RuntimeError("Not connected to IMAP server")

        limit = limit or self.config.batch_size

        try:
            # Select inbox
            self._connection.select("INBOX")

            # Search for unseen messages
            status, message_ids = self._connection.search(None, "UNSEEN")
            if status != "OK":
                logger.error(f"Failed to search for unseen messages: {status}")
                return []

            # Get message IDs
            ids = message_ids[0].split()
            if not ids:
                logger.info("No unseen messages found")
                return []

            # Limit number of messages
            ids = ids[:limit]
            logger.info(f"Found {len(ids)} unseen messages (limit: {limit})")

            # Fetch emails
            emails = []
            for msg_id in ids:
                try:
                    raw_email = self._fetch_email(msg_id)
                    if raw_email:
                        emails.append(raw_email)

                        # Mark as read if configured
                        if self.config.mark_as_read:
                            self._connection.store(msg_id, "+FLAGS", "\\Seen")

                except Exception as e:
                    logger.error(f"Error fetching email {msg_id}: {e}")
                    continue

            logger.info(f"Successfully fetched {len(emails)} emails")
            return emails

        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            raise

    def _fetch_email(self, msg_id: bytes) -> RawEmail | None:
        """Fetch a single email by ID.

        Args:
            msg_id: Message ID

        Returns:
            RawEmail or None if failed
        """
        try:
            # Fetch email data
            if not self._connection:
                return None

            status, msg_data = self._connection.fetch(msg_id.decode(), "(RFC822)")
            if (
                status != "OK"
                or not msg_data
                or not isinstance(msg_data, list)
                or len(msg_data) == 0
            ):
                msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                status_str = status.decode() if isinstance(status, bytes) else status
                logger.error(f"Failed to fetch message {msg_id_str}: {status_str}")
                return None

            # Parse email - msg_data is a list of tuples
            email_tuple = msg_data[0]
            if not isinstance(email_tuple, tuple) or len(email_tuple) < 2:
                return None

            raw_email_data = email_tuple[1]
            if isinstance(raw_email_data, bytes):
                email_message = email.message_from_bytes(raw_email_data)
            else:
                return None

            # Extract headers
            message_id = email_message.get("Message-ID", "").strip()
            sender = email_message.get("From", "").strip()
            subject = self._decode_header(email_message.get("Subject", ""))
            date_str = email_message.get("Date", "")

            # Parse date
            received_at = self._parse_date(date_str)

            # Extract body
            body_plain = None
            body_html = None

            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))

                    # Skip attachments
                    if "attachment" in content_disposition:
                        continue

                    if content_type == "text/plain" and not body_plain:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            body_plain = payload.decode("utf-8", errors="ignore")
                    elif content_type == "text/html" and not body_html:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            body_html = payload.decode("utf-8", errors="ignore")
            else:
                content_type = email_message.get_content_type()
                payload = email_message.get_payload(decode=True)
                if payload and isinstance(payload, bytes):
                    body_text = payload.decode("utf-8", errors="ignore")
                    if content_type == "text/plain":
                        body_plain = body_text
                    elif content_type == "text/html":
                        body_html = body_text

            return RawEmail(
                message_id=message_id,
                sender=sender,
                subject=subject,
                body_plain=body_plain,
                body_html=body_html,
                received_at=received_at,
                uid=int(msg_id),
            )

        except Exception as e:
            msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
            logger.error(f"Error parsing email {msg_id_str}: {e}")
            return None

    def _decode_header(self, header: str) -> str:
        """Decode email header.

        Args:
            header: Raw header string

        Returns:
            Decoded header string
        """
        decoded_parts = []
        for part, encoding in decode_header(header):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(encoding or "utf-8", errors="ignore"))
            else:
                decoded_parts.append(part)
        return " ".join(decoded_parts)

    def _parse_date(self, date_str: str) -> datetime:
        """Parse email date string.

        Args:
            date_str: Date string from email header

        Returns:
            Parsed datetime
        """
        try:
            from email.utils import parsedate_to_datetime

            return parsedate_to_datetime(date_str)
        except Exception:
            logger.warning(f"Failed to parse date: {date_str}, using current time")
            return datetime.utcnow()
