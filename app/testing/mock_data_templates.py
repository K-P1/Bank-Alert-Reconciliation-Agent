"""
Shared templates and data for mock transaction and email generation.

This module contains common data structures used by both MockTransactionClient
and MockEmailGenerator to ensure consistency and high match rates.
"""

import random
from typing import Dict, List, Any, Literal


# Transaction templates for realistic data generation
TRANSACTION_TEMPLATES = [
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
NIGERIAN_BANKS = [
    "GTB",
    "FirstBank",
    "Access",
    "Zenith",
    "UBA",
    "Fidelity",
    "Union",
    "Stanbic",
]


# Bank email and alert details
BANK_DETAILS = {
    "GTB": {
        "sender": "alerts@gtbank.com",
        "name": "GTBank",
        "alert_prefix": "GTB ALERT",
    },
    "FirstBank": {
        "sender": "alerts@firstbanknigeria.com",
        "name": "FirstBank",
        "alert_prefix": "FirstBank Alert",
    },
    "Access": {
        "sender": "notifications@accessbankplc.com",
        "name": "AccessBank",
        "alert_prefix": "Access Alert",
    },
    "Zenith": {
        "sender": "alerts@zenithbank.com",
        "name": "Zenith Bank",
        "alert_prefix": "Zenith Alert",
    },
    "UBA": {
        "sender": "alerts@ubagroup.com",
        "name": "UBA",
        "alert_prefix": "UBA ALERT",
    },
    "Fidelity": {
        "sender": "alerts@fidelitybank.ng",
        "name": "Fidelity Bank",
        "alert_prefix": "Fidelity Alert",
    },
    "Union": {
        "sender": "alerts@unionbankng.com",
        "name": "Union Bank",
        "alert_prefix": "Union Alert",
    },
    "Stanbic": {
        "sender": "alerts@stanbicibtc.com",
        "name": "Stanbic IBTC",
        "alert_prefix": "Stanbic Alert",
    },
}


def generate_transaction_description(template: Dict[str, Any]) -> tuple[str, str]:
    """
    Generate a transaction description from a template.
    
    Args:
        template: Transaction template with description pattern and data
        
    Returns:
        Tuple of (formatted_description, detail_value)
    """
    # Extract the detail value based on template keys
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

    # Format the description
    description: str = str(template["description"]).format(
        merchant=detail,
        name=detail,
        location=detail,
        company=detail,
        network=detail,
        charge_type=detail,
    )

    return description, detail


def generate_realistic_amount(description: str) -> float:
    """
    Generate a realistic transaction amount based on description.
    
    Args:
        description: Transaction description
        
    Returns:
        Transaction amount in NGN
    """
    if "Salary" in description:
        return round(random.uniform(50000, 500000), 2)
    elif "ATM" in description or "POS" in description:
        return round(random.uniform(1000, 50000), 2)
    elif "Airtime" in description:
        return float(random.choice([100, 200, 500, 1000, 2000, 5000]))
    elif "Bank Charge" in description:
        return round(random.uniform(10, 500), 2)
    else:
        return round(random.uniform(500, 100000), 2)


def generate_reference(bank: str, timestamp) -> str:
    """
    Generate a realistic bank reference code.
    
    Args:
        bank: Bank identifier (e.g., 'GTB', 'Access')
        timestamp: Transaction timestamp
        
    Returns:
        Reference code string
    """
    ref_num = random.randint(100000, 999999)
    return f"{bank}/TRF/{ref_num}/{timestamp.strftime('%y%m%d')}"


def generate_account_number() -> str:
    """
    Generate a masked account number.
    
    Returns:
        Masked account string (e.g., '****1234')
    """
    return f"****{random.randint(1000, 9999)}"


def generate_balance() -> float:
    """
    Generate a realistic account balance.
    
    Returns:
        Balance amount in NGN
    """
    return round(random.uniform(10000, 1000000), 2)
