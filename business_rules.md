# Business Rules — AI-Driven Dynamic Discounting & Liquidity Engine
**Status:** LOCKED FINAL (superseding v2). This is the source of truth for the DB schema, ML labels, optimizer, and datasets. Downstream code, schemas, and models must strictly adhere to these locked decisions.

---

## 1. Buyer Risk Tiers

Buyers are scored 0–100 (overall buyer score) and bucketed into a tier. Tier drives the max allowed discount (Section 4) and the optimizer's constraints.

| Tier | Score Range | Meaning |
|---|---|---|
| Tier A | score >= 80 | Reliable payer, low delay history |
| Tier B | 50 <= score < 80 | Moderate delay history or exposure |
| Tier C | score < 50 | Frequent late payment or high outstanding balance |

### Buyer Score Formulas
All three sub-scores are scored 0–100 and are **higher-is-better**:

- **Payment Reliability:**
  ```
  Reliability = 50 × (1 − late_rate)
              + 25 × (1 − min(avg_days_late / 15, 1))
              + 25 × (1 − late_rate_of_last_5_settled)
  ```

- **Financial Exposure:**
  ```
  Financial = 100 × (1 − min(open_exposure / credit_limit, 1))
  ```

- **Liquidity Health:**
  ```
  Liquidity = 100 × (1 − min(overdue_open_exposure / open_exposure, 1))
  ```
  *(If `open_exposure = 0`, `Liquidity = 100`)*

- **Overall Buyer Score:**
  ```
  Overall Buyer Score = 0.80 × Reliability + 0.10 × Financial + 0.10 × Liquidity
  ```
  *(Note: The previous `0.40 * payment_reliability + 0.35 * financial_risk + 0.25 * liquidity_risk` 40/35/25 formula is superseded).*

### Cold Start Rule
For buyers with **fewer than 5 resolved invoices**:
- Assigned provisional **Tier B**
- **Never Tier A**
- Set `tier_basis = cold_start`

---

## 2. Payment Delay Labeling & Severe Delay

### ML Target
The ML target remains strictly **binary**:
- `is_late = 1` if paid after `due_date`
- `is_late = 0` otherwise (paid on or before `due_date`)

### Severe Late Flag & Escalation
- `severe_late = days_late > 30`
- For open invoices: `overdue_days > 30 -> ESCALATE`
- **Do not turn `severe_late` into a separate ML target** (binary classification target remains `is_late`).

### Dataset Distribution
- Historical dataset late rate is **approximately 34%** (supersedes the outdated 15–20% estimate).

### Training vs. Inference Invoices
- Invoices with no `payment_date` yet (still outstanding) are **excluded** from training labels but **included** in inference (the operational target of prediction).

### Leakage Rule
Never use `payment_date`, `payment_status`, or anything computed after the invoice was issued as a feature — only as the label. This is the #1 way dynamic discounting models silently fail.

---

## 3. Dispute Handling & ML Leakage Prevention

`disputed` must **NOT** be used as an ML feature because the timing of dispute availability at invoice issuance is not established and creates feature leakage.

### ML Feature Policy
Remove from primary ML features:
- `disputed`
- `buyer_hist_dispute_rate`

### Business Layer Policy
- Disputed invoices are **ineligible / HOLD**.
- Check current invoice dispute status at recommendation time.
- Check dispute status again immediately before release.
- **Do NOT create a buyer-level dispute scoring rule.**

---

## 4. Discount Rates & Tier Caps

- **Allowed discount grid:**
  - `0.5%`
  - `1.0%`
  - `1.5%`
- **Optimizer range:** `0.5% – 1.5%` (tested in grid increments; supersedes old 0.5%–3.0% range).
- **Max allowed discount by tier (Policy Ceiling):**
  | Tier | Max Discount | Policy Note |
  |---|---|---|
  | Tier A | 1.5% | Cap reduced to 1.5% |
  | Tier B | 1.0% | Cap reduced to 1.0% |
  | Tier C | 0.5% | Discouraged; high-risk buyers rarely get incentives |
- **Liquidity URGENT Exception:** Under `URGENT` liquidity conditions, Tier C may be relaxed up to `1.0%` maximum (see Section 7).
- **Minimum invoice amount eligible for discounting:** `₹50,000` (supersedes old ₹1,00,000 cutoff).
- **Minimum days remaining to due date:** `days_until_due >= 10` days (an invoice due in under 10 days does not provide meaningful cash acceleration).

---

## 5. Eligibility Criteria for a Discount Offer

An invoice is **eligible** for a discount offer only if **ALL** of the following hold:
1. Invoice is open/unpaid (`payment_status = unpaid`, not already paid or offered/pending)
2. Invoice is not overdue (`overdue_days == 0`)
3. `days_until_due >= 10`
4. Invoice is not disputed (`is_disputed = False` / not on hold)
5. `invoice_amount >= ₹50,000` (do not use the old ₹1,00,000 minimum)
6. Buyer Tier allows discounts: Tier A and Tier B are eligible; Tier C is excluded unless liquidity status is `URGENT`

---

## 6. Optimizer Objective & Constraints

```
Expected Business Value = Liquidity Benefit − Discount Cost − Risk/Constraint Penalty
```

### Operational Formulation
- `Liquidity Benefit` = `invoice_amount × P(late) × delay_cost_factor` (value of securing cash now vs. waiting)
- `Discount Cost` = `invoice_amount × discount_rate`
- `Risk/Constraint Penalty` = 0 if within tier cap, else ∞ (infeasible)

### Hard Constraints
- **Discount rate ≤ tier max** (Section 4).
- **Weekly discount budget constraint:**
  Total discount cost across all offers in a batch ≤ `weekly_budget`, calculated as:
  ```
  weekly_budget = clamp(
      0.015 × total eligible invoice value,
      minimum ₹30,000,
      maximum ₹1,00,000
  )
  ```
  *(Important: Use **eligible invoice value** as the base, not total open invoice value).*
- **Per-buyer offer frequency:**
  - Maximum **one offer per buyer per run**.
  - A buyer must have **at least 14 days since the previous non-rejected offer** before receiving another offer.
- **On-time filter:** Never offer a discount if predicted `on_time_probability >= 90%` AND no urgent liquidity gap exists (avoid paying buyers who would pay on time anyway).

---

## 7. Liquidity Gap → Urgency Rule

- If forecasted 7-day net liquidity is **negative**, mark liquidity status as `URGENT`.
- If forecasted 30-day net liquidity is negative but 7-day is positive, mark as `WATCH`.
- Otherwise `HEALTHY`.
- Under `URGENT`, the optimizer is allowed to relax the Tier C discount cap up to `1.0%` max, enabling cash generation from riskier counterparties during verified shortfalls.

---

## 8. Human Approval Governance

Human approval is required when:
```
discount_amount > ₹1,000
OR
invoice_amount > ₹1,00,000
```
*(Do not use the old ₹20,000 / ₹10,00,000 thresholds).*

- **Strict AI boundaries:** The AI/LLM cannot change `discount_offers.status` directly — only an authorized human action via the approved API endpoint can advance status from `recommended` → `offered`.
- **Audit trail:** Every approval or rejection is logged to `audit_logs` with `user_id`, `timestamp`, and the full recommendation payload.

---

## 9. Amount Units & Model/Business Boundary

- Business/DB/runtime = ₹
- ML CSVs = ₹000
- Training loader converts monetary ML fields to ₹ by multiplying by 1,000 where required.
- Seed-data/business loaders convert ₹000 monetary display fields to ₹ exactly once.
- Ratios are unitless.
- No double conversion.

---

## 10. Payment Terms & Dataset Limitations

- **Net 30 Only:** The current dataset contains Net 30 only (`due_date = invoice_date + 30 days`).
- **Documented Limitation:** This is a documented dataset limitation.
- **Dynamic Logic:** Business logic must calculate eligibility from the actual `due_date` / `days_until_due` dynamically rather than hard-coding 30.
- **Integrity Rule:** Do **NOT** artificially add 60/90-day records.

---

## 11. Simulated Offer History Governance

- Existing simulated offer history is **demonstration history only**.
- It **must NOT be used for ML training or tuning**.
- Required metadata tags:
  ```
  data_origin = SIMULATED_DEMONSTRATION_OFFER_HISTORY
  ml_use_allowed = 0
  ```

---

## 12. Data Field → Rule Mapping (Synthetic Generator Specifications)

- Buyers must have a `payment_reliability` score calculated using the Section 1 formula.
- Historical dataset late rate is approximately **34%** (supersedes 15–20%).
- Strict Net 30 terms observed across all invoice generations.

---

## Decisions Log (Locked Final Decisions)

**Q1 — Gross invoice amount or net margin for discount cost?**
**Decision: Gross amount.** Net margin requires COGS data not available; estimating it synthetically adds noise without credibility. Documented as a stated simplification in the README, not hidden.

**Q2 — Fixed or scaling weekly discount budget?**
**Decision: Scaling on eligible invoice value.**
`weekly_budget = clamp(0.015 × total eligible invoice value, min=₹30,000, max=₹1,00,000)`.
Tying it to 1.5% of eligible invoice value ensures scalability across varying portfolio sizes while keeping budget controlled. (Supersedes total open invoice value).

**Q3 — Per-buyer discount frequency cap?**
**Decision: Maximum 1 offer per buyer per run, and at least 14 days since previous non-rejected offer.** Prevents offer spamming and keeps negotiation pacing realistic.

**Q4 — Buyer score formula update?**
**Decision: 80/10/10 weighting (Reliability 80%, Financial 10%, Liquidity 10%).** Supersedes the previous 40/35/25 split to heavily prioritize proven payment behavior while factoring exposure and liquidity.

**Q5 — Human approval thresholds?**
**Decision: Lowered to `discount_amount > ₹1,000` OR `invoice_amount > ₹1,00,000`.** Protects margin on smaller high-rate discounts and monitors material invoice movements.

**Q6 — Dispute feature policy?**
**Decision: Exclude from ML features completely (`disputed`, `buyer_hist_dispute_rate`).** Prevents target leakage at invoice issuance; handled exclusively as a business eligibility gate.

**Q7 — Currency unit consistency?**
**Decision: ₹ in DB/runtime, ₹000 in ML CSVs.** Converted strictly at the model boundary.