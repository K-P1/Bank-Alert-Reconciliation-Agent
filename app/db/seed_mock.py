"""
Seed database with dynamically generated mock data.

This script generates matching emails and transactions using the same
templates and data sources to ensure high match rates for testing.

Usage:
    python -m app.db.seed_mock [num_transactions] [num_emails] [hours_back] [clear]

Examples:
    # Default: 50 transactions, 40 emails, 72 hours
    python -m app.db.seed_mock

    # Custom amounts
    python -m app.db.seed_mock 100 80 48

    # Clear existing data first (prompts for confirmation)
    python -m app.db.seed_mock 100 80 48 true
    
    # Add to existing data (default behavior)
    python -m app.db.seed_mock 50 40 24 false
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from app.db.unit_of_work import UnitOfWork
from app.transactions.clients.mock_client import MockTransactionClient
from app.emails.mock_email_generator import MockEmailGenerator


async def seed_with_mock_data(
    num_transactions: int = 50,
    num_emails: int = 40,
    hours_back: int = 72,
    clear_existing: bool = False,
    match_rate: float = 0.7,
):
    """
    Seed database with dynamically generated mock data.
    
    Args:
        num_transactions: Number of transactions to generate
        num_emails: Number of emails to generate
        hours_back: Time range to spread the data over (hours)
        clear_existing: If True, clear existing data before seeding
        match_rate: Fraction of emails that should match transactions (0.0 to 1.0)
    """
    async with UnitOfWork() as uow:
        print("=" * 70)
        print("🌱 Seeding database with dynamically generated mock data")
        print("=" * 70)
        
        # Check existing data
        email_count = await uow.emails.count()
        transaction_count = await uow.transactions.count()
        
        if email_count > 0 or transaction_count > 0:
            print(f"\n⚠️  Database already contains data:")
            print(f"   - {email_count} emails")
            print(f"   - {transaction_count} transactions")
            
            if clear_existing:
                print("\n🗑️  Clearing existing data...")
                
                # Delete all emails
                deleted_emails = await uow.emails.delete_all()
                print(f"   ✓ Deleted {deleted_emails} emails")
                
                # Delete all transactions
                deleted_txns = await uow.transactions.delete_all()
                print(f"   ✓ Deleted {deleted_txns} transactions")
                
                # Delete all matches (if any)
                try:
                    deleted_matches = await uow.matches.delete_all()
                    if deleted_matches > 0:
                        print(f"   ✓ Deleted {deleted_matches} matches")
                except Exception:
                    pass  # Matches table might not exist or be empty
                
                await uow.commit()
                print("   ✅ Database cleared successfully!")
            else:
                response = input("\nContinue and add more data? (y/n): ")
                if response.lower() != "y":
                    print("❌ Seeding cancelled.")
                    return

        # Setup time range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)
        
        print(f"\n📅 Time range: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"   ({hours_back} hours)")
        
        # Calculate how many should match
        num_matching = int(num_emails * match_rate)
        num_unmatched_emails = num_emails - num_matching
        num_unmatched_transactions = num_transactions - num_matching
        
        print(f"\n🎯 Match strategy:")
        print(f"   - {num_matching} matching email-transaction pairs")
        print(f"   - {num_unmatched_emails} unmatched emails (no transaction)")
        print(f"   - {num_unmatched_transactions} unmatched transactions (no email)")
        print(f"   - Target match rate: {match_rate*100:.0f}%")
        
        # Phase 1: Generate matching pairs
        print(f"\n💰 Phase 1: Generating {num_matching} matching email-transaction pairs...")
        client = MockTransactionClient()
        generator = MockEmailGenerator()
        
        matching_transactions = []
        matching_emails = []
        time_span = (end_time - start_time).total_seconds()
        
        for i in range(num_matching):
            # Generate random timestamp within range
            random_seconds = random.uniform(0, time_span)
            tx_time = start_time + timedelta(seconds=random_seconds)
            
            # Generate transaction
            raw_txn = client._generate_transaction(tx_time)
            matching_transactions.append(raw_txn)
            
            # Generate matching email with SAME amount and reference
            # Add small time offset (email typically arrives slightly after transaction)
            email_time = tx_time + timedelta(seconds=random.uniform(1, 300))  # 1-5 min delay
            
            # Create email that matches this transaction
            matching_email = generator._generate_matching_email(
                amount=raw_txn.amount,
                reference=raw_txn.reference or "",
                description=raw_txn.description or "",
                timestamp=email_time,
                tx_type=raw_txn.transaction_type or "debit",
            )
            matching_emails.append(matching_email)
        
        print(f"   ✓ Generated {len(matching_transactions)} matching pairs")
        
        # Phase 2: Generate unmatched transactions
        print(f"\n💰 Phase 2: Generating {num_unmatched_transactions} unmatched transactions...")
        unmatched_transactions = await client.fetch_transactions(
            start_time=start_time,
            end_time=end_time,
            limit=num_unmatched_transactions,
        )
        print(f"   ✓ Generated {len(unmatched_transactions)} unmatched transactions")
        
        # Phase 3: Generate unmatched emails
        print(f"\n📧 Phase 3: Generating {num_unmatched_emails} unmatched emails...")
        unmatched_emails = generator.generate_emails(
            count=num_unmatched_emails,
            start_time=start_time,
            end_time=end_time,
        )
        print(f"   ✓ Generated {len(unmatched_emails)} unmatched emails")
        
        # Combine all transactions and emails
        all_transactions = matching_transactions + unmatched_transactions
        all_emails = matching_emails + unmatched_emails
        
        # Shuffle to make them realistic (not grouped)
        random.shuffle(all_transactions)
        random.shuffle(all_emails)
        
        print(f"\n📊 Total generated:")
        print(f"   - {len(all_transactions)} transactions")
        print(f"   - {len(all_emails)} emails")
        
        # Store transactions
        print("\n💾 Storing transactions in database...")
        stored_count = 0
        skipped_count = 0
        
        for raw_txn in all_transactions:
            try:
                # Check if exists
                existing = await uow.transactions.get_by_transaction_id(
                    raw_txn.transaction_id
                )
                if existing:
                    skipped_count += 1
                    continue
                
                # Create transaction
                await uow.transactions.create(
                    transaction_id=raw_txn.transaction_id,
                    external_source=raw_txn.metadata.get("source", "mock") if raw_txn.metadata else "mock",
                    amount=raw_txn.amount,
                    currency=raw_txn.currency,
                    transaction_type=raw_txn.transaction_type,
                    account_ref=raw_txn.account_reference,
                    description=raw_txn.description,
                    reference=raw_txn.reference,
                    customer_name=raw_txn.customer_name,
                    customer_email=raw_txn.customer_email,
                    transaction_timestamp=raw_txn.timestamp,
                    status="pending",
                )
                stored_count += 1
                
            except Exception as e:
                print(f"   ✗ Error storing transaction {raw_txn.transaction_id}: {e}")
        
        print(f"   ✓ Stored {stored_count} transactions")
        if skipped_count > 0:
            print(f"   ⊘ Skipped {skipped_count} duplicates")
        
        # Store emails
        print("\n💾 Storing emails in database...")
        stored_count = 0
        skipped_count = 0
        
        for email_data in all_emails:
            try:
                # Check if exists
                existing = await uow.emails.get_by_message_id(email_data["message_id"])
                if existing:
                    skipped_count += 1
                    continue
                
                # Create email
                await uow.emails.create(**email_data)
                stored_count += 1
                
            except Exception as e:
                print(f"   ✗ Error storing email {email_data['message_id']}: {e}")
        
        print(f"   ✓ Stored {stored_count} emails")
        if skipped_count > 0:
            print(f"   ⊘ Skipped {skipped_count} duplicates")
        
        # Commit all changes
        await uow.commit()
        
        # Print summary
        print("\n" + "=" * 70)
        print("✅ Mock data seeding completed successfully!")
        print("=" * 70)
        
        final_email_count = await uow.emails.count()
        final_transaction_count = await uow.transactions.count()
        
        print(f"\n📊 Database summary:")
        print(f"   - Total emails: {final_email_count}")
        print(f"   - Total transactions: {final_transaction_count}")
        
        print(f"\n🎯 Expected match statistics:")
        print(f"   - Matching pairs: {num_matching}")
        print(f"   - Unmatched emails: {num_unmatched_emails}")
        print(f"   - Unmatched transactions: {num_unmatched_transactions}")
        print(f"   - Expected match rate: {match_rate*100:.0f}%")
        
        print("\n💡 Next steps:")
        print("   1. Run reconciliation: POST /a2a/agent/BARA")
        print("   2. Check matches in database")
        print("   3. Adjust parameters and re-run if needed")
        print()


if __name__ == "__main__":
    import sys
    
    # Parse command line arguments
    num_txns = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    num_emails = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    hours = int(sys.argv[3]) if len(sys.argv) > 3 else 72
    clear = sys.argv[4].lower() in ['true', 'yes', 'y', '1'] if len(sys.argv) > 4 else False
    
    print(f"Parameters:")
    print(f"  - Transactions: {num_txns}")
    print(f"  - Emails: {num_emails}")
    print(f"  - Time span: {hours} hours")
    print(f"  - Clear existing: {clear}")
    print()
    
    if clear:
        print("⚠️  WARNING: This will DELETE all existing data!")
        confirm = input("Are you sure? Type 'yes' to confirm: ")
        if confirm.lower() != 'yes':
            print("❌ Cancelled.")
            sys.exit(0)
        print()
    
    asyncio.run(seed_with_mock_data(
        num_transactions=num_txns,
        num_emails=num_emails,
        hours_back=hours,
        clear_existing=clear,
    ))
