"""Tests for database models and repositories."""

import pytest
from datetime import datetime, timedelta
from app.db.unit_of_work import UnitOfWork


@pytest.mark.asyncio
class TestEmailRepository:
    """Test Email model and repository."""

    async def test_create_email(self):
        """Test creating an email record."""
        async with UnitOfWork() as uow:
            email = await uow.emails.create(
                message_id="test-001@test.com",
                sender="alerts@bank.com",
                subject="Test Alert",
                body="Test email body",
                amount=1000.00,
                currency="NGN",
                reference="TEST/REF/001",
                email_timestamp=datetime.utcnow(),
            )

            assert email.id is not None
            assert email.message_id == "test-001@test.com"
            assert email.amount == 1000.00
            assert email.currency == "NGN"
            await uow.commit()

    async def test_get_by_message_id(self):
        """Test retrieving email by message ID."""
        async with UnitOfWork() as uow:
            # Create email
            await uow.emails.create(
                message_id="test-002@test.com",
                sender="alerts@bank.com",
                subject="Test Alert 2",
                body="Test body",
                amount=2000.00,
                currency="NGN",
            )
            await uow.commit()

        async with UnitOfWork() as uow:
            # Retrieve email
            email = await uow.emails.get_by_message_id("test-002@test.com")
            assert email is not None
            assert email.amount == 2000.00

    async def test_get_unprocessed_emails(self):
        """Test getting unprocessed emails."""
        async with UnitOfWork() as uow:
            # Create unprocessed email
            email = await uow.emails.create(
                message_id="test-unprocessed@test.com",
                sender="alerts@bank.com",
                subject="Unprocessed",
                body="Body",
                is_processed=False,
            )
            await uow.commit()

        async with UnitOfWork() as uow:
            unprocessed = await uow.emails.get_unprocessed()
            assert len(unprocessed) > 0
            assert any(e.message_id == "test-unprocessed@test.com" for e in unprocessed)

    async def test_mark_as_processed(self):
        """Test marking email as processed."""
        async with UnitOfWork() as uow:
            email = await uow.emails.create(
                message_id="test-mark-processed@test.com",
                sender="alerts@bank.com",
                subject="Test",
                body="Body",
                is_processed=False,
            )
            await uow.commit()

            # Mark as processed
            updated = await uow.emails.mark_as_processed(email.id)
            assert updated is not None
            assert updated.is_processed is True
            await uow.commit()


@pytest.mark.asyncio
class TestTransactionRepository:
    """Test Transaction model and repository."""

    async def test_create_transaction(self):
        """Test creating a transaction record."""
        async with UnitOfWork() as uow:
            transaction = await uow.transactions.create(
                transaction_id="TEST-TXN-001",
                external_source="paystack",
                amount=5000.00,
                currency="NGN",
                transaction_timestamp=datetime.utcnow(),
                status="pending",
            )

            assert transaction.id is not None
            assert transaction.transaction_id == "TEST-TXN-001"
            assert transaction.amount == 5000.00
            await uow.commit()

    async def test_get_by_transaction_id(self):
        """Test retrieving transaction by ID."""
        async with UnitOfWork() as uow:
            await uow.transactions.create(
                transaction_id="TEST-TXN-002",
                external_source="flutterwave",
                amount=3000.00,
                currency="NGN",
                transaction_timestamp=datetime.utcnow(),
            )
            await uow.commit()

        async with UnitOfWork() as uow:
            transaction = await uow.transactions.get_by_transaction_id("TEST-TXN-002")
            assert transaction is not None
            assert transaction.amount == 3000.00

    async def test_get_unverified_transactions(self):
        """Test getting unverified transactions."""
        async with UnitOfWork() as uow:
            await uow.transactions.create(
                transaction_id="TEST-TXN-UNVERIFIED",
                external_source="paystack",
                amount=7000.00,
                currency="NGN",
                transaction_timestamp=datetime.utcnow(),
                is_verified=False,
            )
            await uow.commit()

        async with UnitOfWork() as uow:
            unverified = await uow.transactions.get_unverified()
            assert len(unverified) > 0
            assert any(t.transaction_id == "TEST-TXN-UNVERIFIED" for t in unverified)

    async def test_mark_as_verified(self):
        """Test marking transaction as verified."""
        async with UnitOfWork() as uow:
            transaction = await uow.transactions.create(
                transaction_id="TEST-TXN-VERIFY",
                external_source="paystack",
                amount=9000.00,
                currency="NGN",
                transaction_timestamp=datetime.utcnow(),
                is_verified=False,
            )
            await uow.commit()

            # Mark as verified
            updated = await uow.transactions.mark_as_verified(transaction.id)
            assert updated is not None
            assert updated.is_verified is True
            assert updated.status == "verified"
            await uow.commit()


@pytest.mark.asyncio
class TestMatchRepository:
    """Test Match model and repository."""

    async def test_create_match(self):
        """Test creating a match record."""
        async with UnitOfWork() as uow:
            # Create email and transaction first
            email = await uow.emails.create(
                message_id="test-match-email@test.com",
                sender="alerts@bank.com",
                subject="Test",
                body="Body",
                amount=10000.00,
            )
            transaction = await uow.transactions.create(
                transaction_id="TEST-MATCH-TXN",
                external_source="paystack",
                amount=10000.00,
                currency="NGN",
                transaction_timestamp=datetime.utcnow(),
            )

            # Create match
            match = await uow.matches.create_match(
                email_id=email.id,
                transaction_id=transaction.id,
                matched=True,
                confidence=0.95,
                match_method="exact",
            )

            assert match.id is not None
            assert match.email_id == email.id
            assert match.transaction_id == transaction.id
            assert match.confidence == 0.95
            await uow.commit()

    async def test_get_matched(self):
        """Test getting matched records."""
        async with UnitOfWork() as uow:
            email = await uow.emails.create(
                message_id="test-get-matched@test.com",
                sender="alerts@bank.com",
                subject="Test",
                body="Body",
            )
            transaction = await uow.transactions.create(
                transaction_id="TEST-GET-MATCHED-TXN",
                external_source="paystack",
                amount=5000.00,
                currency="NGN",
                transaction_timestamp=datetime.utcnow(),
            )

            await uow.matches.create_match(
                email_id=email.id,
                transaction_id=transaction.id,
                matched=True,
                confidence=0.88,
            )
            await uow.commit()

        async with UnitOfWork() as uow:
            matched = await uow.matches.get_matched()
            assert len(matched) > 0
            assert all(m.matched is True for m in matched)

    async def test_get_match_statistics(self):
        """Test getting match statistics."""
        async with UnitOfWork() as uow:
            stats = await uow.matches.get_match_statistics()
            assert "total" in stats
            assert "matched" in stats
            assert "unmatched" in stats
            assert "average_confidence" in stats
            assert "match_rate" in stats


@pytest.mark.asyncio
class TestConfigRepository:
    """Test Config model and repository."""

    async def test_set_and_get_value(self):
        """Test setting and getting config values."""
        async with UnitOfWork() as uow:
            # Set value
            await uow.config.set_value(
                key="test.setting",
                value=42,
                value_type="int",
                description="Test setting",
            )
            await uow.commit()

        async with UnitOfWork() as uow:
            # Get value
            value = await uow.config.get_value("test.setting")
            assert value == 42

    async def test_get_by_category(self):
        """Test getting configs by category."""
        async with UnitOfWork() as uow:
            await uow.config.set_value(
                key="category.test.1",
                value="value1",
                category="test_category",
            )
            await uow.config.set_value(
                key="category.test.2",
                value="value2",
                category="test_category",
            )
            await uow.commit()

        async with UnitOfWork() as uow:
            configs = await uow.config.get_by_category("test_category")
            assert len(configs) >= 2


@pytest.mark.asyncio
class TestLogRepository:
    """Test Log model and repository."""

    async def test_create_log(self):
        """Test creating a log entry."""
        async with UnitOfWork() as uow:
            log = await uow.logs.create_log(
                level="INFO",
                event="test_event",
                message="Test log message",
                component="test_component",
            )

            assert log.id is not None
            assert log.level == "INFO"
            assert log.event == "test_event"
            await uow.commit()

    async def test_get_errors(self):
        """Test getting error logs."""
        async with UnitOfWork() as uow:
            await uow.logs.create_log(
                level="ERROR",
                event="test_error",
                message="Test error message",
            )
            await uow.commit()

        async with UnitOfWork() as uow:
            errors = await uow.logs.get_errors(hours=24)
            assert len(errors) > 0
            assert all(log.level in ["ERROR", "CRITICAL"] for log in errors)


@pytest.mark.asyncio
class TestUnitOfWork:
    """Test Unit of Work pattern."""

    async def test_commit(self):
        """Test committing changes."""
        async with UnitOfWork() as uow:
            email = await uow.emails.create(
                message_id="test-uow-commit@test.com",
                sender="test@test.com",
                subject="Test",
                body="Body",
            )
            email_id = email.id

        # Verify it was committed
        async with UnitOfWork() as uow:
            email = await uow.emails.get_by_id(email_id)
            assert email is not None

    async def test_rollback_on_exception(self):
        """Test automatic rollback on exception."""
        email_id = None
        try:
            async with UnitOfWork() as uow:
                email = await uow.emails.create(
                    message_id="test-uow-rollback@test.com",
                    sender="test@test.com",
                    subject="Test",
                    body="Body",
                )
                email_id = email.id
                # Simulate an error
                raise Exception("Test error")
        except Exception:
            pass

        # Verify it was rolled back
        async with UnitOfWork() as uow:
            email = await uow.emails.get_by_id(email_id) if email_id else None
            # Should be None since transaction was rolled back
            assert email is None
