"""Sample email data for testing and development."""

from datetime import datetime, timedelta

# Sample bank alert emails
SAMPLE_EMAILS = [
    {
        "message_id": "email-001@alerts.bank.com",
        "sender": "alerts@firstbank.com",
        "subject": "Transaction Alert: Credit",
        "body": """
Dear Customer,

Your account has been credited with NGN 25,000.00.

Transaction Details:
Amount: NGN 25,000.00
Reference: FBN/TRF/123456789
Date: 2025-11-04 10:15:00
Account: ****5678
Sender: John Doe

Balance: NGN 125,000.00

Thank you for banking with us.
        """,
        "amount": 25000.00,
        "currency": "NGN",
        "reference": "FBN/TRF/123456789",
        "account_info": "****5678",
        "email_timestamp": datetime.utcnow() - timedelta(hours=2),
        "received_at": datetime.utcnow() - timedelta(hours=2),
        "parsing_confidence": 0.95,
        "is_processed": False,
    },
    {
        "message_id": "email-002@alerts.bank.com",
        "sender": "alerts@gtbank.com",
        "subject": "Debit Transaction Notification",
        "body": """
GTBank Transaction Alert

Acct: 0123456789
Date: 04-Nov-2025 14:30:22
Desc: POS Purchase
Amt: NGN 5,500.00
Bal: NGN 45,200.00
Ref: GTB/POS/987654321
        """,
        "amount": 5500.00,
        "currency": "NGN",
        "reference": "GTB/POS/987654321",
        "account_info": "0123456789",
        "email_timestamp": datetime.utcnow() - timedelta(hours=1),
        "received_at": datetime.utcnow() - timedelta(hours=1),
        "parsing_confidence": 0.88,
        "is_processed": False,
    },
    {
        "message_id": "email-003@alerts.bank.com",
        "sender": "notifications@accessbank.com",
        "subject": "Credit Alert",
        "body": """
AccessBank Alert

Your account ending with 4321 has been credited.

Amount: N150,000.00
Transaction Ref: ACC2025110400123
Date/Time: 04/11/2025 09:00:15 AM
Description: Salary Payment
Available Balance: N850,000.00
        """,
        "amount": 150000.00,
        "currency": "NGN",
        "reference": "ACC2025110400123",
        "account_info": "****4321",
        "email_timestamp": datetime.utcnow() - timedelta(hours=5),
        "received_at": datetime.utcnow() - timedelta(hours=5),
        "parsing_confidence": 0.92,
        "is_processed": False,
    },
    {
        "message_id": "email-004@alerts.bank.com",
        "sender": "alerts@zenithbank.com",
        "subject": "Transaction Successful",
        "body": """
Dear Valued Customer,

This is to inform you that a transaction was completed on your account.

Transaction Type: Credit
Amount: NGN 75,000.00
Reference Number: ZEN/WEB/456789012
Transaction Date: 04-NOV-2025 16:45:33
Account Number: 2233445566
Narration: Online Transfer from Jane Smith

Current Balance: NGN 200,000.00

Zenith Bank - Your trusted partner
        """,
        "amount": 75000.00,
        "currency": "NGN",
        "reference": "ZEN/WEB/456789012",
        "account_info": "2233445566",
        "email_timestamp": datetime.utcnow() - timedelta(minutes=30),
        "received_at": datetime.utcnow() - timedelta(minutes=30),
        "parsing_confidence": 0.97,
        "is_processed": False,
    },
    {
        "message_id": "email-005@alerts.bank.com",
        "sender": "alerts@ubagroup.com",
        "subject": "UBA Transaction Alert",
        "body": """
UBA ALERT

Acct: ****7890
Amt: NGN 12,750.50
Txn Type: ATM Withdrawal
Date: 04/11/2025 18:22:10
Ref: UBA/ATM/111222333
Location: Lagos Island
Bal: NGN 87,249.50

Need help? Call 0700-CALL-UBA
        """,
        "amount": 12750.50,
        "currency": "NGN",
        "reference": "UBA/ATM/111222333",
        "account_info": "****7890",
        "email_timestamp": datetime.utcnow() - timedelta(minutes=15),
        "received_at": datetime.utcnow() - timedelta(minutes=15),
        "parsing_confidence": 0.90,
        "is_processed": False,
    },
]
