"""
Mock transaction API client for testing and development.

Generates realistic Nigerian bank transaction data for testing
the poller without requiring real API credentials.
"""

import random
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from app.transactions.clients.base import (
    BaseTransactionClient,
    RawTransaction,
    APIConnectionError,
)
from app.testing.mock_data_templates import (
    TRANSACTION_TEMPLATES,
    NIGERIAN_BANKS,
    generate_transaction_description,
    generate_realistic_amount,
    generate_reference,
    generate_account_number,
)


class MockTransactionClient(BaseTransactionClient):
    """
    Mock API client that generates realistic test transactions.

    Simulates Nigerian payment providers (Paystack, Flutterwave, etc.)
    with realistic transaction patterns and occasional failures.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        failure_rate: float = 0.0,
        latency_ms: int = 100,
    ):
        """
        Initialize mock client.

        Args:
            api_key: Ignored (mock doesn't need auth)
            base_url: Ignored (mock doesn't make real requests)
            timeout: Simulated timeout
            failure_rate: Probability of simulated failure (0.0 to 1.0)
            latency_ms: Simulated network latency in milliseconds
        """
        super().__init__(api_key, base_url, timeout)
        self.failure_rate = failure_rate
        self.latency_ms = latency_ms
        self._transaction_counter = 0

    def get_source_name(self) -> str:
        """Return source identifier."""
        return "mock"

    async def validate_credentials(self) -> bool:
        """Mock credential validation always succeeds."""
        await self._simulate_latency()
        return True

    async def fetch_transactions(
        self,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RawTransaction]:
        """
        Generate mock transactions within the time range.

        Args:
            start_time: Start of time range
            end_time: End of time range (defaults to now)
            limit: Maximum transactions to return
            offset: Pagination offset

        Returns:
            List of generated transactions
        """
        # Simulate network latency
        await self._simulate_latency()

        # Simulate occasional failures
        if random.random() < self.failure_rate:
            raise APIConnectionError("Simulated API connection failure")

        if end_time is None:
            end_time = datetime.now(timezone.utc)

        # Generate transactions
        transactions = []
        time_span = (end_time - start_time).total_seconds()

        # Generate exactly 'limit' transactions for predictability
        # (Previously was random between 0 and limit*1.2)
        num_transactions = limit

        for i in range(num_transactions):
            # Random timestamp within range
            random_seconds = random.uniform(0, time_span)
            tx_time = start_time + timedelta(seconds=random_seconds)

            transactions.append(self._generate_transaction(tx_time))

        # Sort by timestamp descending (newest first)
        transactions.sort(key=lambda x: x.timestamp, reverse=True)

        # Apply pagination
        return transactions[offset : offset + limit]

    async def get_transaction_by_id(
        self, transaction_id: str
    ) -> Optional[RawTransaction]:
        """
        Fetch a single transaction by ID.

        For mock client, returns None (not implemented for simplicity).
        """
        await self._simulate_latency()
        return None

    def _generate_transaction(self, timestamp: datetime) -> RawTransaction:
        """Generate a single realistic transaction."""
        self._transaction_counter += 1

        # Pick a random template
        template = random.choice(TRANSACTION_TEMPLATES)
        tx_type: str = str(template["type"])

        # Generate description with realistic details
        description, detail = generate_transaction_description(template)

        # Generate realistic amount based on transaction type
        amount = generate_realistic_amount(description)

        # Generate reference codes
        bank = random.choice(NIGERIAN_BANKS)
        reference = generate_reference(bank, timestamp)

        # Generate transaction ID
        tx_id = f"TXN{timestamp.strftime('%Y%m%d')}{self._transaction_counter:06d}"

        # Generate customer info (for credits)
        customer_name = None
        customer_email = None
        if tx_type == "credit" and "Transfer" in description:
            customer_name = detail  # Name is already in description
            # Generate email from name
            name_parts = customer_name.lower().split()
            if len(name_parts) >= 2:
                customer_email = f"{name_parts[0]}.{name_parts[-1]}@example.com"

        return RawTransaction(
            transaction_id=tx_id,
            amount=amount,
            currency="NGN",
            timestamp=timestamp,
            description=description,
            reference=reference,
            customer_name=customer_name,
            customer_email=customer_email,
            account_reference=generate_account_number(),
            transaction_type=tx_type,
            status="success",
            metadata={
                "source": "mock",
                "bank": bank,
                "channel": random.choice(["web", "mobile", "pos", "atm"]),
            },
        )

    async def _simulate_latency(self):
        """Simulate network latency."""
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)
