"""Seed database with sample data for development and testing."""

import asyncio
from app.db.unit_of_work import UnitOfWork
from tests.fixtures.sample_emails import SAMPLE_EMAILS  # type: ignore[import-not-found, attr-defined]
from tests.fixtures.sample_transactions import SAMPLE_TRANSACTIONS  # type: ignore[import-not-found, attr-defined]


async def seed_database():
    """Seed the database with sample emails and transactions."""
    async with UnitOfWork() as uow:
        print("Seeding database with sample data...")

        # Check if data already exists
        email_count = await uow.emails.count()
        transaction_count = await uow.transactions.count()

        if email_count > 0 or transaction_count > 0:
            print("Database already contains data:")
            print(f"  - {email_count} emails")
            print(f"  - {transaction_count} transactions")
            response = input("Do you want to continue and add more data? (y/n): ")
            if response.lower() != "y":
                print("Seeding cancelled.")
                return

        # Seed emails
        print(f"\nSeeding {len(SAMPLE_EMAILS)} sample emails...")
        for email_data in SAMPLE_EMAILS:
            try:
                # Check if email already exists
                existing = await uow.emails.get_by_message_id(email_data["message_id"])
                if existing:
                    print(f"  - Skipping {email_data['message_id']} (already exists)")
                    continue

                email = await uow.emails.create(**email_data)
                print(
                    f"  ✓ Created email: {email.message_id} "
                    f"(Amount: {email.currency} {email.amount})"
                )
            except Exception as e:
                print(f"  ✗ Error creating email {email_data['message_id']}: {e}")

        # Seed transactions
        print(f"\nSeeding {len(SAMPLE_TRANSACTIONS)} sample transactions...")
        for txn_data in SAMPLE_TRANSACTIONS:
            try:
                # Check if transaction already exists
                existing = await uow.transactions.get_by_transaction_id(
                    txn_data["transaction_id"]
                )
                if existing:
                    print(f"  - Skipping {txn_data['transaction_id']} (already exists)")
                    continue

                transaction = await uow.transactions.create(**txn_data)
                print(
                    f"  ✓ Created transaction: {transaction.transaction_id} "
                    f"(Amount: {transaction.currency} {transaction.amount})"
                )
            except Exception as e:
                print(
                    f"  ✗ Error creating transaction {txn_data['transaction_id']}: {e}"
                )

        # Seed some default config values
        print("\nSeeding default configuration...")
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

        for config_data in default_configs:
            try:
                existing = await uow.config.get_by_key(config_data["key"])
                if existing:
                    print(f"  - Skipping {config_data['key']} (already exists)")
                    continue

                config = await uow.config.create(**config_data)
                print(f"  ✓ Created config: {config.key} = {config.value}")
            except Exception as e:
                print(f"  ✗ Error creating config {config_data['key']}: {e}")

        await uow.commit()
        print("\n✅ Database seeding completed successfully!")

        # Print summary
        email_count = await uow.emails.count()
        transaction_count = await uow.transactions.count()
        config_count = await uow.config.count()

        print("\nDatabase summary:")
        print(f"  - Total emails: {email_count}")
        print(f"  - Total transactions: {transaction_count}")
        print(f"  - Total configs: {config_count}")


if __name__ == "__main__":
    asyncio.run(seed_database())
