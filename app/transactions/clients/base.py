"""
Base transaction API client interface.

Defines the contract that all transaction API clients must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from pydantic import BaseModel


class RawTransaction(BaseModel):
    """Raw transaction data from external API before normalization."""

    transaction_id: str
    amount: float
    currency: str
    timestamp: datetime
    description: Optional[str] = None
    reference: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    account_reference: Optional[str] = None
    transaction_type: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    # Pydantic v2: prefer model_dump for serialization; no custom Config needed


class BaseTransactionClient(ABC):
    """
    Abstract base class for transaction API clients.

    All transaction API integrations (Paystack, Flutterwave, etc.)
    must implement this interface.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the client.

        Args:
            api_key: API authentication key
            base_url: Base URL for the API
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    @abstractmethod
    async def fetch_transactions(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RawTransaction]:
        """
        Fetch transactions from the API.

        Args:
            start_time: Fetch transactions after this time
            end_time: Fetch transactions before this time (defaults to now)
            limit: Maximum number of transactions to fetch
            offset: Pagination offset

        Returns:
            List of raw transaction objects

        Raises:
            APIConnectionError: If connection to API fails
            APIAuthenticationError: If authentication fails
            APIRateLimitError: If rate limit exceeded
        """
        pass

    @abstractmethod
    async def get_transaction_by_id(
        self, transaction_id: str
    ) -> Optional[RawTransaction]:
        """
        Fetch a single transaction by ID.

        Args:
            transaction_id: Unique transaction identifier

        Returns:
            Raw transaction object or None if not found
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Validate API credentials.

        Returns:
            True if credentials are valid, False otherwise
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """
        Get the name of this transaction source.

        Returns:
            Source identifier (e.g., 'paystack', 'flutterwave', 'mock')
        """
        pass

    def normalize_transaction(self, raw: RawTransaction) -> Dict[str, Any]:
        """
        Normalize raw transaction to internal schema.

        Args:
            raw: Raw transaction from API

        Returns:
            Dictionary matching the Transaction model schema
        """
        return {
            "transaction_id": raw.transaction_id,
            "amount": raw.amount,
            "currency": raw.currency.upper() if raw.currency else "NGN",
            "transaction_timestamp": raw.timestamp,
            "description": raw.description or "",
            "reference": raw.reference or "",
            "customer_name": raw.customer_name,
            "customer_email": raw.customer_email,
            "account_ref": raw.account_reference or "",
            "transaction_type": raw.transaction_type or "credit",
            "status": raw.status or "success",
            "external_source": self.get_source_name(),
            "raw_data": json.dumps(raw.model_dump(), default=str),
            "is_verified": False,
        }


class APIError(Exception):
    """Base exception for API client errors."""

    pass


class APIConnectionError(APIError):
    """Raised when connection to API fails."""

    pass


class APIAuthenticationError(APIError):
    """Raised when API authentication fails."""

    pass


class APIRateLimitError(APIError):
    """Raised when API rate limit is exceeded."""

    pass


class APIValidationError(APIError):
    """Raised when API returns invalid data."""

    pass
