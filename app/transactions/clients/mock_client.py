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

        # Mock transaction templates for realistic data
        self._transaction_templates = [
            {
                "description": "POS Purchase - {merchant}",
                "type": "debit",
                "merchants": [
                    "ShopRite Lagos",
                    "Spar Supermarket",
                    "Total Filling Station",
                    "Chicken Republic",
                    "Mr Biggs Restaurant",
                ],
            },
            {
                "description": "Transfer from {name}",
                "type": "credit",
                "names": [
                    "Adebayo Oluwaseun",
                    "Chidinma Okafor",
                    "Ibrahim Musa",
                    "Ngozi Eze",
                    "Babajide Williams",
                ],
            },
            {
                "description": "ATM Withdrawal - {location}",
                "type": "debit",
                "locations": [
                    "Ikeja GRA",
                    "Victoria Island",
                    "Lekki Phase 1",
                    "Surulere",
                    "Yaba",
                ],
            },
            {
                "description": "Salary Payment - {company}",
                "type": "credit",
                "companies": [
                    "ABC Limited",
                    "XYZ Corporation",
                    "Tech Solutions Ltd",
                    "Global Services",
                    "Premium Industries",
                ],
            },
            {
                "description": "Airtime Recharge - {network}",
                "type": "debit",
                "networks": ["MTN", "Glo", "Airtel", "9mobile"],
            },
            {
                "description": "Bank Charge - {charge_type}",
                "type": "debit",
                "charge_types": [
                    "SMS Alert Fee",
                    "Maintenance Fee",
                    "Transfer Fee",
                    "COT",
                ],
            },
        ]

        # Nigerian banks for reference generation
        self._banks = [
            "GTB",
            "FirstBank",
            "Access",
            "Zenith",
            "UBA",
            "Fidelity",
            "Union",
            "Stanbic",
        ]

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

        # Generate between 0 and limit transactions
        num_transactions = min(limit, random.randint(0, int(limit * 1.2)))

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
        template = random.choice(self._transaction_templates)
        tx_type: str = str(template["type"])

        # Generate description with realistic details
        detail: str
        if "merchants" in template:
            detail = str(random.choice(template["merchants"]))
        elif "names" in template:
            detail = str(random.choice(template["names"]))
        elif "locations" in template:
            detail = str(random.choice(template["locations"]))
        elif "companies" in template:
            detail = str(random.choice(template["companies"]))
        elif "networks" in template:
            detail = str(random.choice(template["networks"]))
        elif "charge_types" in template:
            detail = str(random.choice(template["charge_types"]))
        else:
            detail = "Transaction"

        description: str = str(template["description"]).format(
            merchant=detail,
            name=detail,
            location=detail,
            company=detail,
            network=detail,
            charge_type=detail,
        )

        # Generate realistic amounts based on transaction type
        if "Salary" in description:
            amount = round(random.uniform(50000, 500000), 2)
        elif "ATM" in description or "POS" in description:
            amount = round(random.uniform(1000, 50000), 2)
        elif "Airtime" in description:
            amount = round(random.choice([100, 200, 500, 1000, 2000, 5000]), 2)
        elif "Bank Charge" in description:
            amount = round(random.uniform(10, 500), 2)
        else:
            amount = round(random.uniform(500, 100000), 2)

        # Generate reference codes
        bank = random.choice(self._banks)
        ref_num = random.randint(100000, 999999)
        reference = f"{bank}/TRF/{ref_num}/{timestamp.strftime('%y%m%d')}"

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
            account_reference=f"****{random.randint(1000, 9999)}",
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
