# Data Dictionary — AI-Driven Dynamic Discounting & Supply Chain Liquidity Engine

## 1. Dataset Overview

The project uses invoice, buyer, cash-flow, and discount-offer datasets.

| Dataset | Rows | Purpose |
|---|---:|---|
| `invoices_merged_clean.csv` | 5,000 | Master invoice/payment dataset |
| `buyers_clean.csv` | 130 | Buyer master/reference data |
| `daily_cash_flow_clean.csv` | 1,201 | Daily liquidity/cash-flow data |
| `discount_offers_clean.csv` | 300 | Historical/simulated discount-offer data |
| `train.csv` | 3,465 | ML training split |
| `validation.csv` | 649 | ML validation split |
| `test.csv` | 457 | ML test split |
| `scoring.csv` | 429 | Scoring dataset |

## 2. Invoice Dataset

### Key fields

| Field | Meaning | Unit / Notes |
|---|---|---|
| `invoice_id` | Unique invoice identifier | Identifier |
| `buyer_id` | Buyer identifier | Identifier |
| `supplier_id` | Supplier identifier | Identifier |
| `country_code` | Buyer/country code | Text |
| `invoice_date` | Invoice creation date | Date |
| `due_date` | Contractual payment due date | Date |
| `payment_terms_days` | Contractual payment term | Days |
| `invoice_amount` | Invoice amount used by ML dataset | ₹000 |
| `invoice_amount_display` | Invoice amount for business/display use | ₹ |
| `disputed` | Whether invoice is disputed | 0/1 |
| `paperless_bill` | Whether the invoice is Paper or Electronic \| Paper/Electronic |
| `invoice_month` | Month extracted from invoice date | Integer |
| `invoice_dow` | Day of week extracted from invoice date | Integer |
| `buyer_prior_invoice_count` | Prior invoices for buyer | Count |
| `buyer_hist_late_rate` | Historical late-payment rate | 0–1 |
| `buyer_hist_avg_delay_days` | Historical average payment delay | Days |
| `buyer_hist_delay_std` | Historical delay standard deviation | Days |
| `buyer_hist_max_delay` | Maximum historical delay | Days |
| `buyer_last_invoice_delay` | Delay on previous settled invoice | Days |
| `buyer_days_since_last_invoice` | Days since previous invoice | Days |
| `buyer_hist_dispute_rate` | Historical dispute rate | 0–1 |
| `buyer_hist_avg_amount` | Historical average invoice amount | ₹000 |
| `amount_vs_buyer_avg_ratio` | Invoice amount / buyer average amount | Ratio |
| `outstanding_amount_at_invoice` | Open exposure at invoice creation | ₹000 |
| `outstanding_count_at_invoice` | Open invoice count at invoice creation | Count |
| `has_history` | Whether buyer has sufficient history | 0/1 |
| `is_late` | ML target: payment was late | 0/1 |

### Target

`is_late` is the primary ML target.

Across the 4,746 settled invoices, 1,594 were late, giving an overall late-payment rate of approximately **33.6%**.

### Severe late

A payment is classified as severe late when:

`days_late > 30`

There are **20 severe-late settled invoices** in the dataset.

The ML target remains binary (`is_late`). Severe late is handled as a business/risk rule and is not a separate ML target.

## 3. Leakage and Outcome Fields

The following fields are outcome/future-derived and must not be used as predictive ML features:

- `settled_date`
- `days_to_settle`
- `days_late`
- `delay_bucket`
- `invoice_status`
- `days_until_due`
- `discount_eligible_flag`
- `record_source`
- `split`
- `split_prior_report`

Identifiers such as `invoice_id` and `buyer_id` are also not used as predictive features.

`disputed` is retained in the source/business data, but is excluded from the primary ML feature set because the timing of dispute information at invoice issuance is not sufficiently established.

`buyer_hist_dispute_rate` is also excluded from the primary ML feature set.

## 4. Disputed Invoices

Disputed invoices are held out from discount eligibility at the business layer.

The dataset contains:

- 1,154 disputed invoices overall
- 65 disputed open invoices
- 1,089 disputed settled invoices

The final decision is invoice-level: a disputed invoice is not eligible for a discount offer.

There is no buyer-level dispute penalty in the final buyer-tier formula.

## 5. Discount Eligibility

An invoice is eligible only when all conditions are satisfied:

1. Invoice status is `open`
2. `days_until_due >= 10`
3. `disputed = 0`
4. Invoice amount is at least ₹50,000
5. Buyer is not excluded by the applicable business rules
6. Tier C buyers are excluded unless the liquidity-urgent mode is enabled

The original dataset contained 67 invoices with `discount_eligible_flag = 1`.

After recomputation using the final eligibility rules:

- Eligible invoices: **54**
- Flag mismatches: **13**

The cleaned seed dataset contains the recomputed flag.

## 6. Payment Terms

All 5,000 invoices currently have:

`payment_terms_days = 30`

and the due date follows the 30-day payment term.

The project therefore documents **Net 30 only**.

No artificial 60-day or 90-day payment-term records are added merely to create variety.

Business logic uses the actual `due_date` and `days_until_due` fields rather than hard-coding a 30-day assumption.

## 7. Monetary Units

The ML/source CSV datasets store monetary values in **₹000 (thousands of Indian Rupees)** unless explicitly stated otherwise.

### Invoice dataset

- `invoice_amount` → ₹000
- `invoice_amount_display` → ₹
- Other invoice monetary features such as `outstanding_amount_at_invoice` → ₹000

### Buyer dataset (`buyers_clean.csv`)

- `total_invoiced_amount` → ₹000
- `open_exposure_amount` → ₹000
- `credit_limit` → ₹000

### Cash-flow dataset (`daily_cash_flow_clean.csv`)

- `inflow_actual` → ₹000
- `outflow_actual` → ₹000
- `net_cash_flow` → ₹000
- `opening_balance` → ₹000
- `closing_balance` → ₹000
- `outstanding_receivables` → ₹000
- `min_cash_buffer` → ₹000
- `liquidity_gap` → ₹000
- `is_weekend` → 0/1 flag, not monetary

### Business layer / database

The business layer and database use **INR (₹)**.

Monetary conversion is performed exactly once at the ML/business boundary.

Examples:

- ML value `50.39` → business value ₹50,390
- ML value `100.00` → business value ₹100,000

Ratios such as `amount_vs_buyer_avg_ratio` are unitless and must not be multiplied by 1,000.
## 8. Buyer Tier

Buyer tier is calculated independently from the ML late-payment probability.

### Reliability

`50 × (1 − late_rate) + 25 × (1 − min(avg_days_late / 15, 1)) + 25 × (1 − late_rate_of_last_5_settled)`

### Financial

`100 × (1 − min(open_exposure / credit_limit, 1))`

### Liquidity

`100 × (1 − min(overdue_open_exposure / open_exposure, 1))`

If there is no open exposure, liquidity score is 100.

### Final Buyer Score

`0.80 × Reliability + 0.10 × Financial + 0.10 × Liquidity`

Tier thresholds:

- **Tier A:** score ≥ 80
- **Tier B:** 50 ≤ score < 80
- **Tier C:** score < 50

Cold-start buyers with fewer than 5 resolved invoices receive provisional Tier B and can never receive Tier A until sufficient history exists.

## 9. Discount Offer Policy

Discount rates use a strict 0.5 percentage-point grid:

- 0.5%
- 1.0%
- 1.5%

Maximum rates:

| Tier | Maximum discount |
|---|---:|
| Tier A | 1.5% |
| Tier B | 1.0% |
| Tier C | 0.5% |
| Tier C — liquidity urgent | 1.0% |

Additional controls:

- At least 14 days since the buyer's previous non-rejected offer
- Maximum one offer per buyer per run
- Existing simulated offers are demonstration history only
- Existing simulated offers are not used for ML training or tuning

## 10. Human Approval

Human approval is required when either condition is true:

- Discount amount > ₹1,000
- Invoice amount > ₹1,00,000

## 11. Weekly Budget

Weekly discount budget is:

`1.5% × eligible invoice value`

The resulting budget is clamped between:

- Minimum: ₹30,000
- Maximum: ₹1,00,000

## 12. ML vs Business Responsibilities

### ML layer

Predicts payment risk:

> Will the invoice be paid late, and with what probability?

### Business layer

Applies deterministic rules:

- Invoice eligibility
- Dispute hold
- Buyer tier
- Due-date checks
- Amount threshold
- Offer cooldown
- Discount caps
- Approval requirements
- Weekly budget

### Discount engine

Converts the eligible/risk-qualified invoice into the final discount offer.

The ML model does **not** directly decide the discount rate.

## 13. Data Lineage

Original source data is kept locally under:

`source_data/`

It is intentionally excluded from Git.

Cleaning/recomputation logic is maintained under:

`scripts/`

Small cleaned datasets intended for reproducible application seeding are stored under:

`seed_data/`

The source invoice dataset is not modified in place.

The cleaned invoice seed file is generated by:

`scripts/clean_invoice_dataset.py`

The generated file is:

`seed_data/invoices_merged_clean.csv`



