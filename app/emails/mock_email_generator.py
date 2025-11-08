"""
Mock email generator for testing and development.

Generates realistic Nigerian bank alert emails that can be matched with
transactions from the MockTransactionClient. Uses the same templates,
banks, and data patterns to ensure high match rates.
"""

import random
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Literal

from app.db.models.email import Email
from app.testing.mock_data_templates import (
    TRANSACTION_TEMPLATES,
    NIGERIAN_BANKS,
    BANK_DETAILS,
    generate_transaction_description,
    generate_realistic_amount,
    generate_reference,
    generate_account_number,
    generate_balance,
)


class MockEmailGenerator:
    """
    Generate realistic bank alert emails that match mock transactions.
    
    This generator uses the same templates and data sources as the
    MockTransactionClient to ensure that generated emails can be
    matched with generated transactions.
    """

    def __init__(self, match_probability: float = 0.8):
        """
        Initialize the mock email generator.
        
        Args:
            match_probability: Probability that a generated email will
                             match a transaction pattern (0.0 to 1.0)
        """
        self.match_probability = match_probability
        self._email_counter = 0

        # Email templates for different banks
        self._email_templates = {
            "formal": """Dear Valued Customer,

This is to inform you that a transaction was completed on your account.

Transaction Type: {tx_type}
Amount: NGN {amount:,.2f}
Reference Number: {reference}
Transaction Date: {timestamp}
Account Number: {account}
Description: {description}

Current Balance: NGN {balance:,.2f}

{bank_name} - Banking made easy
""",
            "short": """{alert_prefix}

Acct: {account}
Amt: NGN {amount:,.2f}
Txn Type: {tx_type_short}
Date: {timestamp_short}
Ref: {reference}
Desc: {description}
Bal: NGN {balance:,.2f}
""",
            "structured": """Transaction Alert - {tx_type}

Account: {account}
Amount: N{amount:,.2f}
Transaction Ref: {reference}
Date/Time: {timestamp_medium}
Description: {description}
Available Balance: N{balance:,.2f}

{bank_name}
""",
        }

    def generate_emails(
        self,
        count: int,
        start_time: datetime,
        end_time: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple mock bank alert emails.
        
        Args:
            count: Number of emails to generate
            start_time: Start of time range
            end_time: End of time range (defaults to now)
            
        Returns:
            List of email dictionaries ready for database insertion
        """
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        emails = []
        time_span = (end_time - start_time).total_seconds()

        for _ in range(count):
            # Random timestamp within range
            random_seconds = random.uniform(0, time_span)
            email_time = start_time + timedelta(seconds=random_seconds)
            
            email = self._generate_single_email(email_time)
            emails.append(email)

        # Sort by timestamp descending (newest first)
        emails.sort(key=lambda x: x["email_timestamp"], reverse=True)

        return emails

    def _generate_single_email(self, timestamp: datetime) -> Dict[str, Any]:
        """Generate a single realistic bank alert email."""
        self._email_counter += 1

        # Pick a random template
        template = random.choice(TRANSACTION_TEMPLATES)
        tx_type: Literal["credit", "debit"] = template["type"]  # type: ignore

        # Generate description with realistic details
        description, detail = generate_transaction_description(template)

        # Generate realistic amounts based on transaction type
        amount = generate_realistic_amount(description)

        # Generate reference codes
        bank = random.choice(NIGERIAN_BANKS)
        reference = generate_reference(bank, timestamp)

        # Get bank details
        bank_info = BANK_DETAILS[bank]
        
        # Generate account number
        account = generate_account_number()
        
        # Generate balance
        balance = generate_balance()
        
        # Pick email template style
        template_style = random.choice(["formal", "short", "structured"])
        email_template = self._email_templates[template_style]
        
        # Format timestamp for different styles
        timestamp_short = timestamp.strftime("%d-%b-%Y %H:%M:%S")
        timestamp_medium = timestamp.strftime("%d/%m/%Y %I:%M:%S %p")
        
        # Transaction type formatting
        tx_type_display = "Credit" if tx_type == "credit" else "Debit"
        tx_type_short = "CR" if tx_type == "credit" else "DR"
        
        # Generate email body
        body = email_template.format(
            alert_prefix=bank_info["alert_prefix"],
            bank_name=bank_info["name"],
            tx_type=tx_type_display,
            tx_type_short=tx_type_short,
            amount=amount,
            reference=reference,
            timestamp=timestamp.strftime("%d-%b-%Y %H:%M:%S"),
            timestamp_short=timestamp_short,
            timestamp_medium=timestamp_medium,
            account=account,
            description=description,
            balance=balance,
        )
        
        # Generate subject
        subject_templates = [
            f"Transaction Alert: {tx_type_display}",
            f"{tx_type_display} Transaction Notification",
            f"{bank_info['alert_prefix']} - {tx_type_display}",
            f"Account {tx_type_display} Alert",
        ]
        subject = random.choice(subject_templates)
        
        # Generate message ID
        message_id = (
            f"<mock-email-{self._email_counter}-"
            f"{timestamp.strftime('%Y%m%d%H%M%S')}@{bank.lower()}.alerts.com>"
        )
        
        # Determine parsing confidence (higher for well-structured emails)
        if template_style == "formal":
            confidence = round(random.uniform(0.85, 0.98), 2)
        elif template_style == "structured":
            confidence = round(random.uniform(0.80, 0.95), 2)
        else:
            confidence = round(random.uniform(0.70, 0.90), 2)

        return {
            "message_id": message_id,
            "sender": bank_info["sender"],
            "subject": subject,
            "body": body,
            "amount": amount,
            "currency": "NGN",
            "reference": reference,
            "account_info": account,
            "email_timestamp": timestamp,
            "received_at": timestamp,
            "parsing_confidence": confidence,
            "confidence": confidence,  # Alias
            "parsing_method": "mock",
            "is_processed": False,
        }

    def _generate_matching_email(
        self,
        amount: float,
        reference: str,
        description: str,
        timestamp: datetime,
        tx_type: str,
    ) -> Dict[str, Any]:
        """
        Generate an email that matches a specific transaction.
        
        Args:
            amount: Transaction amount (must match exactly)
            reference: Transaction reference (must match exactly)
            description: Transaction description
            timestamp: Email timestamp
            tx_type: Transaction type ('credit' or 'debit')
            
        Returns:
            Email dictionary matching the transaction
        """
        self._email_counter += 1
        
        # Extract bank from reference (format: Bank/TRF/123456/YYMMDD)
        bank = reference.split("/")[0] if "/" in reference else random.choice(NIGERIAN_BANKS)
        
        # Get bank details
        bank_info = BANK_DETAILS.get(bank, BANK_DETAILS["GTB"])
        
        # Generate account number and balance
        account = generate_account_number()
        balance = generate_balance()
        
        # Pick template style
        template_style = random.choice(["formal", "short", "structured"])
        template = self._email_templates[template_style]
        
        # Format transaction type
        tx_type_display = tx_type.upper()
        tx_type_short = "CR" if tx_type == "credit" else "DR"
        
        # Generate email body using template
        body = template.format(
            alert_prefix=bank_info["alert_prefix"],
            bank_name=bank_info["name"],
            tx_type=tx_type_display,
            tx_type_short=tx_type_short,
            amount=amount,
            reference=reference,
            timestamp=timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            timestamp_short=timestamp.strftime("%d-%b %H:%M"),
            timestamp_medium=timestamp.strftime("%d/%m/%Y %H:%M"),
            account=account,
            description=description,
            balance=balance,
        )
        
        # Generate subject
        subject_templates = [
            f"{tx_type_display} Transaction Notification",
            f"{bank_info['alert_prefix']} - {tx_type_display}",
            f"Account {tx_type_display} Alert",
        ]
        subject = random.choice(subject_templates)
        
        # Generate message ID
        message_id = (
            f"<mock-email-{self._email_counter}-"
            f"{timestamp.strftime('%Y%m%d%H%M%S')}@{bank.lower()}.alerts.com>"
        )
        
        # High confidence for matching emails
        confidence = round(random.uniform(0.90, 0.99), 2)

        return {
            "message_id": message_id,
            "sender": bank_info["sender"],
            "subject": subject,
            "body": body,
            "amount": amount,
            "currency": "NGN",
            "reference": reference,
            "account_info": account,
            "email_timestamp": timestamp,
            "received_at": timestamp,
            "parsing_confidence": confidence,
            "confidence": confidence,
            "parsing_method": "mock",
            "is_processed": False,
        }


# Convenience function
def generate_mock_emails(
    count: int = 10,
    hours_back: int = 24,
    match_probability: float = 0.8,
) -> List[Dict[str, Any]]:
    """
    Generate mock emails for testing.
    
    Args:
        count: Number of emails to generate
        hours_back: How many hours back to spread the timestamps
        match_probability: Probability of matching transaction patterns
        
    Returns:
        List of email dictionaries
    """
    generator = MockEmailGenerator(match_probability=match_probability)
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours_back)
    
    return generator.generate_emails(count, start_time, end_time)
