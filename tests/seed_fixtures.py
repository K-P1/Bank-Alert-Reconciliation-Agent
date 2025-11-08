"""
Seed database with static test fixtures.

This script loads hardcoded test data from fixtures for:
- Unit tests
- Integration tests
- Debugging specific scenarios

For dynamic mock data generation, use: python -m app.db.seed_mock

Usage:
    python -m tests.seed_fixtures
    # or
    uv run python -m tests.seed_fixtures
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.unit_of_work import UnitOfWork
from tests.fixtures.sample_emails import SAMPLE_EMAILS
from tests.fixtures.sample_transactions import SAMPLE_TRANSACTIONS


async def seed_database():
    """Seed the database with sample emails and transactions from fixtures."""
    async with UnitOfWork() as uow:
        print("=" * 70)
        print("🌱 Seeding database with static test fixtures")
        print("=" * 70)

        # Check if data already exists
        email_count = await uow.emails.count()
        transaction_count = await uow.transactions.count()

        if email_count > 0 or transaction_count > 0:
            print("\n⚠️  Database already contains data:")
            print(f"   - {email_count} emails")
            print(f"   - {transaction_count} transactions")
            response = input("\nContinue and add more data? (y/n): ")
            if response.lower() != "y":
                print("❌ Seeding cancelled.")
                return

        # Seed emails
        print(f"\n📧 Seeding {len(SAMPLE_EMAILS)} sample emails...")
        stored_count = 0
        skipped_count = 0

        for email_data in SAMPLE_EMAILS:
            try:
                # Check if email already exists
                existing = await uow.emails.get_by_message_id(email_data["message_id"])
                if existing:
                    skipped_count += 1
                    continue

                email = await uow.emails.create(**email_data)
                stored_count += 1
                print(f"   ✓ {email.message_id} " f"({email.currency} {email.amount})")
            except Exception as e:
                print(f"   ✗ Error: {email_data['message_id']}: {e}")

        print(f"   ✓ Stored {stored_count} emails")
        if skipped_count > 0:
            print(f"   ⊘ Skipped {skipped_count} duplicates")

        # Seed transactions
        print(f"\n💰 Seeding {len(SAMPLE_TRANSACTIONS)} sample transactions...")
        stored_count = 0
        skipped_count = 0

        for txn_data in SAMPLE_TRANSACTIONS:
            try:
                # Check if transaction already exists
                existing = await uow.transactions.get_by_transaction_id(
                    txn_data["transaction_id"]
                )
                if existing:
                    skipped_count += 1
                    continue

                transaction = await uow.transactions.create(**txn_data)
                stored_count += 1
                print(
                    f"   ✓ {transaction.transaction_id} "
                    f"({transaction.currency} {transaction.amount})"
                )
            except Exception as e:
                print(f"   ✗ Error: {txn_data['transaction_id']}: {e}")

        print(f"   ✓ Stored {stored_count} transactions")
        if skipped_count > 0:
            print(f"   ⊘ Skipped {skipped_count} duplicates")

        # Seed some default config values
        print("\n⚙️  Seeding default configuration...")
        default_configs = [
            {
                "key": "matching.time_window_hours",
                "value": "48",
                "value_type": "int",
                "description": "Time window for matching emails to transactions (hours)",
                "category": "matching",
            },
            {
                "key": "matching.min_confidence_threshold",
                "value": "0.8",
                "value_type": "float",
                "description": "Minimum confidence score to consider a match valid",
                "category": "matching",
            },
            {
                "key": "retention.email_days",
                "value": "30",
                "value_type": "int",
                "description": "How long to keep raw emails (days)",
                "category": "retention",
            },
            {
                "key": "retention.log_days",
                "value": "90",
                "value_type": "int",
                "description": "How long to keep log entries (days)",
                "category": "retention",
            },
        ]

        stored_count = 0
        skipped_count = 0

        for config_data in default_configs:
            try:
                existing = await uow.config.get_by_key(config_data["key"])
                if existing:
                    skipped_count += 1
                    continue

                config = await uow.config.create(**config_data)
                stored_count += 1
                print(f"   ✓ {config.key} = {config.value}")
            except Exception as e:
                print(f"   ✗ Error: {config_data['key']}: {e}")

        print(f"   ✓ Stored {stored_count} configs")
        if skipped_count > 0:
            print(f"   ⊘ Skipped {skipped_count} duplicates")

        await uow.commit()

        # Print summary
        print("\n" + "=" * 70)
        print("✅ Database seeding completed successfully!")
        print("=" * 70)

        email_count = await uow.emails.count()
        transaction_count = await uow.transactions.count()
        config_count = await uow.config.count()

        print("\n📊 Database summary:")
        print(f"   - Total emails: {email_count}")
        print(f"   - Total transactions: {transaction_count}")
        print(f"   - Total configs: {config_count}")

        print("\n💡 Next steps:")
        print("   - Run tests: pytest -v")
        print("   - Run reconciliation: POST /a2a/agent/BARA")
        print()


if __name__ == "__main__":
    asyncio.run(seed_database())
