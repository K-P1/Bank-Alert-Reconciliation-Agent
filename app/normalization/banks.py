"""Centralized Nigerian bank and fintech/microfinance alias/mapping definitions.

This module was extracted from `normalizer.py` (2025-11-07) and extended with a
broader set of Nigerian deposit money banks (DMBs / commercial banks), selected
non-interest banks, and prominent digital / microfinance / fintech banks that
frequently appear in transaction alert emails.

Sources (retrieved 2025-11-07):
- Wikipedia: List of banks in Nigeria (last edit 2025-10-11)
- Official bank websites (selected domains embedded below)
- Public fintech product sites (Kuda, Moniepoint, FairMoney, Carbon)

Structure:
BANK_MAPPINGS: Dict[str, Dict[str, Any]]
  Key: lowercase alias/keyword (no spaces) likely to appear in sender names,
       subjects, or email domains.
  Value: {
    code: Short internal code (NOT official CBN code; chosen for uniqueness)
    name: Canonical full name
    domains: Known official email/web domains (substring match)
    category: commercial | non_interest | fintech | microfinance | holding | dfi
  }

Guidelines for extending:
- Prefer lowercase alias keys without punctuation.
- Include common short forms (e.g., "gtb", "gtbank", "uba", "firstbank").
- Keep codes <= 10 chars, uppercase alphanumeric.
- Add/update domains as encountered in production data.
- Where multiple brands exist (e.g., Standard Chartered vs stanbic), keep them
  separate for more precise enrichment.

NOTE: This list is not exhaustive for all 900+ licensed microfinance banks; it
focuses on widely used digital-facing institutions and major commercial banks.
"""

from __future__ import annotations
from typing import TypedDict, Literal


class BankInfo(TypedDict):
    code: str
    name: str
    domains: list[str]
    category: Literal[
        "commercial", "non_interest", "fintech", "microfinance", "holding", "dfi"
    ]


# Public constant imported by normalizer
BANK_MAPPINGS: dict[str, BankInfo] = {
    # --- Major Commercial Banks (Deposit Money Banks) ---
    "access": {
        "code": "ACC",
        "name": "Access Bank Plc",
        "domains": ["accessbankplc.com", "accessbank.com"],
        "category": "commercial",
    },
    "accessbank": {
        "code": "ACC",
        "name": "Access Bank Plc",
        "domains": ["accessbankplc.com", "accessbank.com"],
        "category": "commercial",
    },
    "gtb": {
        "code": "GTB",
        "name": "Guaranty Trust Bank Plc",
        "domains": ["gtbank.com"],
        "category": "commercial",
    },
    "gtbank": {
        "code": "GTB",
        "name": "Guaranty Trust Bank Plc",
        "domains": ["gtbank.com"],
        "category": "commercial",
    },
    "guaranty": {
        "code": "GTB",
        "name": "Guaranty Trust Bank Plc",
        "domains": ["gtbank.com"],
        "category": "commercial",
    },
    "firstbank": {
        "code": "FBN",
        "name": "First Bank of Nigeria Ltd",
        "domains": ["firstbanknigeria.com", "firstbank.com"],
        "category": "commercial",
    },
    "fbn": {
        "code": "FBN",
        "name": "First Bank of Nigeria Ltd",
        "domains": ["firstbanknigeria.com"],
        "category": "commercial",
    },
    "zenith": {
        "code": "ZEN",
        "name": "Zenith Bank Plc",
        "domains": ["zenithbank.com"],
        "category": "commercial",
    },
    "zenithbank": {
        "code": "ZEN",
        "name": "Zenith Bank Plc",
        "domains": ["zenithbank.com"],
        "category": "commercial",
    },
    "uba": {
        "code": "UBA",
        "name": "United Bank for Africa Plc",
        "domains": ["ubagroup.com", "uba.com"],
        "category": "commercial",
    },
    "unitedbank": {
        "code": "UBA",
        "name": "United Bank for Africa Plc",
        "domains": ["ubagroup.com"],
        "category": "commercial",
    },
    "fcmb": {
        "code": "FCMB",
        "name": "First City Monument Bank Plc",
        "domains": ["fcmb.com"],
        "category": "commercial",
    },
    "stanbic": {
        "code": "STANBIC",
        "name": "Stanbic IBTC Bank Plc",
        "domains": ["stanbicibtc.com"],
        "category": "commercial",
    },
    "stanbicibtc": {
        "code": "STANBIC",
        "name": "Stanbic IBTC Bank Plc",
        "domains": ["stanbicibtc.com"],
        "category": "commercial",
    },
    "standardchartered": {
        "code": "SCB",
        "name": "Standard Chartered Bank Nigeria Ltd",
        "domains": ["sc.com", "standardchartered.com"],
        "category": "commercial",
    },
    "union": {
        "code": "UNION",
        "name": "Union Bank of Nigeria Plc",
        "domains": ["unionbankng.com", "unionbank.com"],
        "category": "commercial",
    },
    "unionbank": {
        "code": "UNION",
        "name": "Union Bank of Nigeria Plc",
        "domains": ["unionbankng.com", "unionbank.com"],
        "category": "commercial",
    },
    "ecobank": {
        "code": "ECO",
        "name": "Ecobank Nigeria Plc",
        "domains": ["ecobank.com"],
        "category": "commercial",
    },
    "fidelity": {
        "code": "FID",
        "name": "Fidelity Bank Plc",
        "domains": ["fidelitybank.ng"],
        "category": "commercial",
    },
    "fidelitybank": {
        "code": "FID",
        "name": "Fidelity Bank Plc",
        "domains": ["fidelitybank.ng"],
        "category": "commercial",
    },
    "sterling": {
        "code": "STERLING",
        "name": "Sterling Bank Plc",
        "domains": ["sterling.ng", "sterlingbankng.com"],
        "category": "commercial",
    },
    "sterlingbank": {
        "code": "STERLING",
        "name": "Sterling Bank Plc",
        "domains": ["sterling.ng"],
        "category": "commercial",
    },
    "wema": {
        "code": "WEMA",
        "name": "Wema Bank Plc",
        "domains": ["wemabank.com"],
        "category": "commercial",
    },
    "wemabank": {
        "code": "WEMA",
        "name": "Wema Bank Plc",
        "domains": ["wemabank.com"],
        "category": "commercial",
    },
    "polaris": {
        "code": "POLARIS",
        "name": "Polaris Bank Plc",
        "domains": ["polarisbanklimited.com"],
        "category": "commercial",
    },
    "polarisbank": {
        "code": "POLARIS",
        "name": "Polaris Bank Plc",
        "domains": ["polarisbanklimited.com"],
        "category": "commercial",
    },
    "keystone": {
        "code": "KEYSTONE",
        "name": "Keystone Bank Ltd",
        "domains": ["keystonebankng.com"],
        "category": "commercial",
    },
    "keystonebank": {
        "code": "KEYSTONE",
        "name": "Keystone Bank Ltd",
        "domains": ["keystonebankng.com"],
        "category": "commercial",
    },
    "unity": {
        "code": "UNITY",
        "name": "Unity Bank Plc",
        "domains": ["unitybankng.com"],
        "category": "commercial",
    },
    "unitybank": {
        "code": "UNITY",
        "name": "Unity Bank Plc",
        "domains": ["unitybankng.com"],
        "category": "commercial",
    },
    "heritage": {
        "code": "HERITAGE",
        "name": "Heritage Bank Plc",
        "domains": ["hbng.com"],
        "category": "commercial",
    },
    "heritagebank": {
        "code": "HERITAGE",
        "name": "Heritage Bank Plc",
        "domains": ["hbng.com"],
        "category": "commercial",
    },
    "providus": {
        "code": "PROVIDUS",
        "name": "Providus Bank Ltd",
        "domains": ["providusbank.com"],
        "category": "commercial",
    },
    "providusbank": {
        "code": "PROVIDUS",
        "name": "Providus Bank Ltd",
        "domains": ["providusbank.com"],
        "category": "commercial",
    },
    "suntrust": {
        "code": "SUNTRUST",
        "name": "SunTrust Bank Nigeria Ltd",
        "domains": ["suntrustng.com", "suntrust.com"],
        "category": "commercial",
    },
    "suntrustbank": {
        "code": "SUNTRUST",
        "name": "SunTrust Bank Nigeria Ltd",
        "domains": ["suntrustng.com"],
        "category": "commercial",
    },
    "titan": {
        "code": "TITAN",
        "name": "Titan Trust Bank Ltd",
        "domains": ["titantrustbank.com"],
        "category": "commercial",
    },
    "titantrust": {
        "code": "TITAN",
        "name": "Titan Trust Bank Ltd",
        "domains": ["titantrustbank.com"],
        "category": "commercial",
    },
    "citibank": {
        "code": "CITI",
        "name": "Citibank Nigeria Ltd",
        "domains": ["citibank.com", "citi.com"],
        "category": "commercial",
    },
    "citibanknigeria": {
        "code": "CITI",
        "name": "Citibank Nigeria Ltd",
        "domains": ["citibank.com"],
        "category": "commercial",
    },
    "globus": {
        "code": "GLOBUS",
        "name": "Globus Bank Ltd",
        "domains": ["globusbank.com"],
        "category": "commercial",
    },
    "globusbank": {
        "code": "GLOBUS",
        "name": "Globus Bank Ltd",
        "domains": ["globusbank.com"],
        "category": "commercial",
    },
    "premiumtrust": {
        "code": "PREMIUM",
        "name": "Premium Trust Bank",
        "domains": ["premiumtrustbank.com"],
        "category": "commercial",
    },
    "premiumtrustbank": {
        "code": "PREMIUM",
        "name": "Premium Trust Bank",
        "domains": ["premiumtrustbank.com"],
        "category": "commercial",
    },
    "signature": {
        "code": "SIGNATURE",
        "name": "Signature Bank Ltd",
        "domains": ["signaturebankng.com"],
        "category": "commercial",
    },
    "signaturebank": {
        "code": "SIGNATURE",
        "name": "Signature Bank Ltd",
        "domains": ["signaturebankng.com"],
        "category": "commercial",
    },
    "parallex": {
        "code": "PARALLEX",
        "name": "Parallex Bank Ltd",
        "domains": ["parallexbank.com"],
        "category": "commercial",
    },
    "parallexbank": {
        "code": "PARALLEX",
        "name": "Parallex Bank Ltd",
        "domains": ["parallexbank.com"],
        "category": "commercial",
    },
    "nova": {
        "code": "NOVA",
        "name": "Nova Commercial Bank Ltd",
        "domains": ["novabank.com.ng", "novabank.com"],
        "category": "commercial",
    },
    "novabank": {
        "code": "NOVA",
        "name": "Nova Commercial Bank Ltd",
        "domains": ["novabank.com.ng"],
        "category": "commercial",
    },
    "optimus": {
        "code": "OPTIMUS",
        "name": "Optimus Bank Ltd",
        "domains": ["optimusbank.com"],
        "category": "commercial",
    },
    "optimusbank": {
        "code": "OPTIMUS",
        "name": "Optimus Bank Ltd",
        "domains": ["optimusbank.com"],
        "category": "commercial",
    },
    # --- Non-Interest Banks ---
    "jaiz": {
        "code": "JAIZ",
        "name": "Jaiz Bank Plc",
        "domains": ["jaizbankplc.com", "jaizbank.com"],
        "category": "non_interest",
    },
    "jaizbank": {
        "code": "JAIZ",
        "name": "Jaiz Bank Plc",
        "domains": ["jaizbankplc.com"],
        "category": "non_interest",
    },
    "lotus": {
        "code": "LOTUS",
        "name": "Lotus Bank Ltd",
        "domains": ["lotusbank.com"],
        "category": "non_interest",
    },
    "lotusbank": {
        "code": "LOTUS",
        "name": "Lotus Bank Ltd",
        "domains": ["lotusbank.com"],
        "category": "non_interest",
    },
    "taj": {
        "code": "TAJ",
        "name": "TAJBank Ltd",
        "domains": ["tajbank.com"],
        "category": "non_interest",
    },
    "tajbank": {
        "code": "TAJ",
        "name": "TAJBank Ltd",
        "domains": ["tajbank.com"],
        "category": "non_interest",
    },
    # --- Prominent Digital / Fintech / Microfinance Banks ---
    "kuda": {
        "code": "KUDA",
        "name": "Kuda Microfinance Bank",
        "domains": ["kuda.com", "joinkuda.com"],
        "category": "fintech",
    },
    "moniepoint": {
        "code": "MONIEPOINT",
        "name": "Moniepoint Microfinance Bank",
        "domains": ["moniepoint.com"],
        "category": "fintech",
    },
    "fairmoney": {
        "code": "FAIRMONEY",
        "name": "FairMoney Microfinance Bank",
        "domains": ["fairmoney.ng"],
        "category": "fintech",
    },
    "carbon": {
        "code": "CARBON",
        "name": "Carbon Microfinance Bank",
        "domains": ["getcarbon.co"],
        "category": "fintech",
    },
    "opay": {
        "code": "OPAY",
        "name": "Opay Digital Services / Wallet",
        "domains": ["opayweb.com", "opay.ng", "opera.com"],
        "category": "fintech",
    },
    "palmpay": {
        "code": "PALMPAY",
        "name": "PalmPay Digital Wallet",
        "domains": ["palmpay.com"],
        "category": "fintech",
    },
    "raven": {
        "code": "RAVEN",
        "name": "Raven Bank (Digital)",
        "domains": ["ravenbank.com"],
        "category": "fintech",
    },
    "sparkle": {
        "code": "SPARKLE",
        "name": "Sparkle Digital Bank",
        "domains": ["sparkle.ng"],
        "category": "fintech",
    },
    "vfd": {
        "code": "VFD",
        "name": "VFD Microfinance Bank",
        "domains": ["vfdbank.com", "vfdgroup.com"],
        "category": "fintech",
    },
    "mint": {
        "code": "MINT",
        "name": "Mint Finex MFB",
        "domains": ["mintyn.com"],
        "category": "fintech",
    },
    "mkobo": {
        "code": "MKOBO",
        "name": "Mkobo Microfinance Bank",
        "domains": ["mkobobank.com"],
        "category": "fintech",
    },
    "cashx": {
        "code": "CASHX",
        "name": "CashX Digital Wallet",
        "domains": ["cashx.ng"],
        "category": "fintech",
    },
    # --- Legacy / Additional Known Microfinance (popular in alerts) ---
    "accion": {
        "code": "ACCION",
        "name": "Accion Microfinance Bank",
        "domains": ["accionmfb.com"],
        "category": "microfinance",
    },
    "lapo": {
        "code": "LAPO",
        "name": "Lapo Microfinance Bank",
        "domains": ["lapomicrofinancebank.com"],
        "category": "microfinance",
    },
    "advans": {
        "code": "ADVANS",
        "name": "Advans La Fayette Microfinance Bank",
        "domains": ["advansnigeria.com"],
        "category": "microfinance",
    },
}

__all__ = ["BANK_MAPPINGS"]
