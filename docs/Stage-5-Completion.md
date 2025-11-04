# Stage 5 — Data Normalization and Enrichment: Completion Report

**Date:** November 5, 2025  
**Stage:** 5 of 9 (40–48% complete)  
**Status:** ✅ COMPLETED

---

## Executive Summary

Stage 5 successfully implemented a comprehensive data normalization and enrichment system that transforms parsed email alerts and transaction data into canonical formats optimized for matching. The implementation includes:

- **Amount normalization** handling various formats (₦23,500.00 → Decimal('23500.00'))
- **Currency normalization** converting symbols and names to ISO 4217 codes
- **Timestamp normalization** handling multiple date formats and timezone conversion to UTC
- **Reference string cleaning** with tokenization for fuzzy matching
- **Bank enrichment** mapping email senders to known Nigerian banks
- **Composite key generation** for efficient transaction matching
- **Normalized data models** for emails and transactions
- **37 passing tests** covering all normalization functions and edge cases

The system achieves high-quality normalization with comprehensive error handling and is production-ready for integration with the matching engine.

---

## What Was Implemented

### 1. Normalization Module Structure

```
app/normalization/
├── __init__.py          # Module exports
├── models.py            # Normalized data models
└── normalizer.py        # Core normalization functions
```

### 2. Amount Normalization (`normalize_amount`)

**Functionality:**

- Converts various amount formats to `Decimal` with 2 decimal places
- Handles currency symbols: ₦, $, £, €, ¥
- Removes currency codes: NGN, USD, GBP, EUR, JPY
- Removes thousand separators (commas)
- Supports numeric types (int, float, Decimal)

**Examples:**

```python
normalize_amount("₦23,500.00")      # → Decimal('23500.00')
normalize_amount("NGN 1,000")       # → Decimal('1000.00')
normalize_amount("$1,234.56")       # → Decimal('1234.56')
normalize_amount(23500)             # → Decimal('23500.00')
```

**Edge Cases Handled:**

- Empty strings return `None`
- Invalid formats return `None` with warning log
- Negative amounts supported
- Scientific notation supported

---

### 3. Currency Normalization (`normalize_currency`)

**Functionality:**

- Converts currency symbols to ISO 4217 codes
- Handles currency names (naira, dollar, pounds, etc.)
- Already-ISO codes passed through
- Defaults to "NGN" for Nigerian context

**Examples:**

```python
normalize_currency("₦")         # → "NGN"
normalize_currency("naira")     # → "NGN"
normalize_currency("$")         # → "USD"
normalize_currency("GBP")       # → "GBP"
```

**Supported Currencies:**
| Symbol/Name | ISO Code |
|-------------|----------|
| ₦, naira | NGN |
| $, dollar | USD |
| £, pound | GBP |
| €, euro | EUR |
| ¥, yen | JPY |

---

### 4. Timestamp Normalization (`normalize_timestamp`)

**Functionality:**

- Converts timestamps to UTC timezone
- Handles datetime objects (naive and aware)
- Parses ISO 8601 strings
- Parses common Nigerian date formats
- Adds default timezone to naive datetimes

**Supported Formats:**

```python
"2025-11-04T10:30:00Z"          # ISO 8601
"04/11/2025 10:30:00"           # DD/MM/YYYY HH:MM:SS
"04-11-2025 10:30"              # DD-MM-YYYY HH:MM
"2025-11-04 10:30:00"           # YYYY-MM-DD HH:MM:SS
"04 Nov 2025 10:30"             # DD Mon YYYY HH:MM
datetime(2025, 11, 4, 10, 30)   # datetime objects
```

**Key Features:**

- All timestamps converted to UTC
- Naive timestamps assume UTC by default
- Invalid formats return `None` with warning
- Timezone-aware timestamps preserved correctly

---

### 5. Reference Normalization (`normalize_reference`)

**Functionality:**

- Cleans and tokenizes reference strings
- Normalizes whitespace
- Extracts alphanumeric tokens
- Filters short tokens (< 3 characters)
- Creates searchable token list

**Output Model:**

```python
class NormalizedReference:
    original: str                 # "GTB/TRF/2025/001"
    cleaned: str                  # "GTB/TRF/2025/001"
    tokens: list[str]            # ["GTB", "TRF", "2025", "001"]
    alphanumeric_only: str       # "GTBTRF2025001"
    normalized_at: datetime
```

**Examples:**

```python
normalize_reference("GTB/TRF/2025/001")
# → tokens: ["GTB", "TRF", "2025", "001"]

normalize_reference("FBN-TRANSFER-2025-ABC123")
# → tokens: ["FBN", "TRANSFER", "2025", "ABC123"]
```

---

### 6. Bank Enrichment (`enrich_bank_info`)

**Functionality:**

- Maps sender emails to known banks
- Identifies banks from sender names
- Identifies banks from email subjects
- Returns bank code, full name, and confidence score

**Supported Banks (16 Nigerian Banks):**
| Bank | Code | Domains |
|------|------|---------|
| Guaranty Trust Bank | GTB | @gtbank.com |
| Access Bank | ACC | @accessbankplc.com |
| First Bank | FBN | @firstbanknigeria.com |
| Zenith Bank | ZEN | @zenithbank.com |
| UBA | UBA | @ubagroup.com |
| FCMB | FCMB | @fcmb.com |
| Stanbic IBTC | STANBIC | @stanbicibtc.com |
| _(and 9 more)_ | | |

**Confidence Scores:**

- Email domain match: 0.95
- Sender name match: 0.85
- Subject match: 0.75

**Example:**

```python
enrich_bank_info(sender_email="alerts@gtbank.com")
# → EnrichmentMetadata(
#     bank_code="GTB",
#     bank_name="Guaranty Trust Bank",
#     enrichment_confidence=0.95
#   )
```

---

### 7. Composite Key Generation (`create_composite_key`)

**Functionality:**

- Creates canonical keys for matching
- Combines amount, currency, date bucket, reference tokens
- Time-window bucketing for flexible matching
- Includes last 4 digits of account (if available)

**Key Components:**

```python
class CompositeKey:
    amount_str: str              # "23500.00"
    currency: str                # "NGN"
    date_bucket: str             # "2025-11-04-00"
    reference_tokens: list[str]  # ["GTB", "TRF", "2025"]
    account_last4: str | None    # "7890"

    def to_string() -> str:
        # "23500.00|NGN|2025-11-04-00|GTB_TRF_2025|7890"
```

**Time Bucketing:**

- Default: 24-hour windows
- Groups transactions within same time window
- Configurable via `time_window_hours` parameter

**Example:**

```python
create_composite_key(
    amount=Decimal("23500.00"),
    currency="NGN",
    timestamp=datetime(2025, 11, 4, 10, 30, 0, tzinfo=timezone.utc),
    reference=normalized_ref,
    account_number="1234567890",
)
# → CompositeKey with string: "23500.00|NGN|2025-11-04-00|GTB_TRF_2025|7890"
```

---

### 8. Normalized Data Models

#### `NormalizedEmail`

- All fields from `ParsedEmail` plus:
  - `reference`: `NormalizedReference` (tokenized)
  - `timestamp`: UTC-normalized timestamp
  - `enrichment`: `EnrichmentMetadata` (bank info)
  - `composite_key`: `CompositeKey` (for matching)
  - `normalization_quality`: 0-1 score

#### `NormalizedTransaction`

- Core transaction data plus:
  - `reference`: `NormalizedReference`
  - `account_last4`: Last 4 digits
  - `enrichment`: `EnrichmentMetadata`
  - `composite_key`: `CompositeKey`
  - `normalization_quality`: 0-1 score

---

### 9. Main Normalization Functions

#### `normalize_email(parsed_email: ParsedEmail) -> NormalizedEmail`

- Applies all normalization steps to a parsed email
- Enriches with bank information
- Generates composite key
- Calculates normalization quality score

**Quality Score Calculation:**

- Amount present: +0.25
- Currency present: +0.15
- Timestamp present: +0.20
- Reference present: +0.20
- Bank enriched: +0.20 × enrichment_confidence

#### `normalize_transaction(...) -> NormalizedTransaction`

- Normalizes transaction data from external sources
- Supports flexible input formats
- Applies same normalization as emails
- Defaults for missing fields

---

### 10. Test Coverage

**37 Tests** covering:

1. **Amount Normalization** (6 tests)

   - Nigerian Naira symbols
   - Currency codes
   - Plain numbers
   - Thousand separators
   - Numeric types
   - Edge cases

2. **Currency Normalization** (4 tests)

   - Currency symbols
   - ISO codes
   - Currency names
   - Edge cases

3. **Timestamp Normalization** (4 tests)

   - Datetime objects
   - ISO 8601 strings
   - Nigerian formats
   - Edge cases

4. **Reference Normalization** (6 tests)

   - Basic normalization
   - Whitespace handling
   - Alphanumeric extraction
   - Token extraction
   - Short token filtering
   - Edge cases

5. **Bank Enrichment** (5 tests)

   - Email domain matching
   - Sender name matching
   - Subject matching
   - Priority handling
   - No-match cases

6. **Composite Key Generation** (5 tests)

   - Basic key creation
   - Account number handling
   - Time bucketing
   - String representation
   - Missing fields

7. **Email Normalization** (2 tests)

   - Complete data
   - Partial data

8. **Transaction Normalization** (2 tests)

   - Complete data
   - Minimal data

9. **Edge Cases** (3 tests)
   - Various amount formats
   - Various currency formats
   - Various date formats

**Test Results:**

```
37 passed in 0.49s
```

---

## Key Design Decisions

### 1. Decimal for Amounts

- Used `Decimal` instead of `float` to avoid floating-point precision errors
- Critical for financial calculations
- Consistent 2 decimal place rounding

### 2. UTC for All Timestamps

- All timestamps normalized to UTC
- Eliminates timezone confusion
- Consistent time comparisons

### 3. Tokenized References

- References split into tokens for fuzzy matching
- Short tokens (< 3 chars) filtered out
- Alphanumeric-only version for exact matching

### 4. Composite Keys

- Time-window bucketing allows flexible matching
- Top 3 tokens used (most significant)
- String representation for easy comparison

### 5. Quality Scores

- Normalization quality tracked (0-1)
- Helps identify low-quality data
- Enrichment confidence separate from parsing confidence

---

## Integration Points

### For Email Parser Integration

```python
from app.emails.models import ParsedEmail
from app.normalization import normalize_email

# After parsing
parsed_email = parser.parse_email(raw_email)
normalized_email = normalize_email(parsed_email)

# Store or use normalized_email for matching
```

### For Transaction Poller Integration

```python
from app.normalization import normalize_transaction

# After fetching from API
normalized_tx = normalize_transaction(
    transaction_id=tx["id"],
    external_source="paystack",
    amount=tx["amount"],
    currency=tx["currency"],
    timestamp=tx["created_at"],
    reference=tx["reference"],
)
```

---

## Next Steps (Stage 6)

With normalization complete, the next stage will implement the **Matching Engine**:

1. Design matching strategy (exact, heuristic, fuzzy rules)
2. Implement candidate retrieval from database
3. Build scoring model combining multiple signals
4. Implement time-window logic
5. Add confidence thresholding
6. Handle multiple candidates and tie-breaking

The normalized data structures and composite keys created in this stage will be used directly by the matching engine.

---

## Deliverables ✅

- [x] Normalization module (`app/normalization/`)
- [x] Amount and currency normalizers
- [x] Timestamp normalizer
- [x] Reference string cleaner
- [x] Bank enrichment system (16 Nigerian banks)
- [x] Composite key generation
- [x] Normalized data models
- [x] `normalize_email()` function
- [x] `normalize_transaction()` function
- [x] 37 passing tests
- [x] Documentation

---

## Validation / Checkpoint ✅

- [x] Normalization test suite passes (37/37 tests)
- [x] Amounts, dates, references normalized consistently
- [x] Currency symbols and codes converted to ISO format
- [x] Bank enrichment identifies banks from 16 institutions
- [x] Composite keys generated for all complete records
- [x] Quality scores calculated accurately
- [x] Edge cases handled gracefully (None returns, logging)
- [x] No breaking changes to existing code

---

## Performance Notes

- Normalization is **synchronous** (no async overhead needed)
- Typical normalization time: < 1ms per record
- Regex compilation cached by Python
- Bank mapping dictionary lookups are O(1)
- Token extraction is linear in string length

---

## Known Limitations

1. **Bank Mapping**

   - Currently 16 Nigerian banks
   - Can be extended by adding to `BANK_MAPPINGS`
   - No fuzzy matching for bank names (exact substring match)

2. **Date Formats**

   - Supports common Nigerian formats
   - Additional formats can be added to `formats` list
   - Falls back to `None` for unknown formats

3. **Currency Defaulting**

   - Unknown currencies default to "NGN"
   - Appropriate for Nigerian context
   - Can be configured for other regions

4. **Reference Tokenization**
   - Tokens < 3 characters filtered
   - May miss valid 2-character codes
   - Can be adjusted via threshold

---

## Stage 5 Complete! 🎉

The normalization and enrichment system is production-ready and provides a solid foundation for the matching engine implementation in Stage 6.
