# Business Rules — AI-Driven Dynamic Discounting & Liquidity Engine
**Status:** Final v2 — agreed by Person A + Person B (Aug 13–14, 2026). This is now the source of truth for the DB schema, ML labels, and optimizer. Changes after this point should be discussed by both, not made unilaterally, since downstream work depends on these numbers being stable.

---

## 1. Buyer Risk Tiers

Buyers are scored 0–100 (overall risk score) and bucketed into a tier. Tier drives the max allowed discount (Section 3) and the optimizer's constraints.

| Tier | Score Range | Meaning |
|---|---|---|
| Tier-A (Low risk) | 80–100 | Reliable payer, low delay history |
| Tier-B (Medium risk) | 50–79 | Some delay history or moderate exposure |
| Tier-C (High risk) | 0–49 | Frequent late payment or high outstanding balance |

**Overall risk score formula (v1, simple weighted average — refine after ML models exist):**
```
overall_risk = 0.4 * payment_reliability + 0.35 * financial_risk + 0.25 * liquidity_risk
```
(each sub-score also 0–100; payment_reliability comes from ML Engine 1, financial_risk and liquidity_risk are business-indicator based for v1, can be model-driven later)

---

## 2. Payment Delay Labeling (for ML training data)

- **On-time**: paid on or before `due_date`
- **Late**: paid after `due_date`
- **Severely late**: paid more than 30 days after `due_date` (flag separately — useful for risk scoring, not just binary classification)
- Invoices with no `payment_date` yet (still outstanding) are **excluded** from training labels but **included** in inference (that's exactly what we're predicting for)

**Leakage rule:** never use `payment_date`, `payment_status`, or anything computed after the invoice was issued as a *feature* — only as the *label*. This is the #1 way this kind of project silently breaks.

---

## 3. Discount Rules

- **Discount range tested by optimizer:** 0.5% – 3.0% (in 0.5% steps), per the doc's example
- **Max allowed discount by tier** (policy ceiling — RAG will also check this against actual policy documents once built):
  | Tier | Max Discount |
  |---|---|
  | Tier-A | 1.75% |
  | Tier-B | 1.25% |
  | Tier-C | 0.5% (discouraged — high risk buyers rarely get early-payment incentives) |
- **Minimum invoice amount eligible for discounting:** ₹1,00,000 (below this, discount admin cost isn't worth it — arbitrary v1 cutoff, revisit)
- **Minimum days remaining to due date to qualify:** 10 days (an invoice due in 3 days isn't a meaningful "early payment" offer)

---

## 4. Eligibility Criteria for a Discount Offer

An invoice is **eligible** for a discount offer only if ALL of the following hold:
1. `payment_status = unpaid` (not already paid or already offered/pending)
2. `days_to_due_date >= 10`
3. `invoice_amount >= ₹1,00,000`
4. Buyer is not flagged `blacklisted` or `disputed`
5. Buyer's tier allows a non-zero discount (Tier-C invoices only get an offer if liquidity need is urgent — see Section 6)

---

## 5. Optimizer Objective (v1)

```
Expected Business Value = Liquidity Benefit − Discount Cost − Risk/Constraint Penalty
```

**v1 simplification (to make it buildable in Week 4):**
- `Liquidity Benefit` = invoice_amount × (probability buyer pays significantly later than X days if not offered a discount) — i.e. value of getting cash now vs. waiting
- `Discount Cost` = invoice_amount × discount_rate
- `Risk/Constraint Penalty` = 0 if within policy tier max, else a large penalty (effectively excludes that discount rate as infeasible)

**Hard constraints:**
- Discount rate ≤ tier max (Section 3)
- Total discount cost across all offers in a batch ≤ weekly discount budget, calculated as:
  ```
  weekly_budget = clamp(0.015 × total_open_invoice_value_this_week, min=₹30,000, max=₹1,00,000)
  ```
  (scales with the actual dataset instead of a fixed number that breaks if invoice volume changes — see Decisions Log, Q2)
- **Per-buyer offer frequency:** a buyer cannot receive more than 1 discount offer per rolling 14-day window, even if multiple invoices are technically eligible (see Decisions Log, Q3)
- Never offer a discount if `on_time_probability >= 90%` AND no urgent liquidity gap exists (don't pay a buyer who was going to pay on time anyway — this is the exact "fixed 2% for everyone is dumb" problem the whole project solves, so enforce it strictly)

---

## 6. Liquidity Gap → Urgency Rule

- If forecasted 7-day net liquidity is **negative**, mark liquidity status as `URGENT`
- If forecasted 30-day net liquidity is negative but 7-day is positive, mark as `WATCH`
- Otherwise `HEALTHY`
- Under `URGENT`, the optimizer is allowed to relax the Tier-C discount rule (Section 3) up to 1% max, since the doc's whole liquidity-crisis scenario (Section 31, "need ₹20L in 7 days") assumes the system can act even on riskier buyers when cash is genuinely tight

---

## 7. Human Approval Rule (non-negotiable, per doc Section 26)

- Any discount offer with `discount_amount > ₹20,000` OR `invoice_amount > ₹10,00,000` requires explicit human approval before status moves from `recommended` → `offered`
- The AI/LLM can never change `discount_offers.status` directly — only a human action via the approved API endpoint can
- Every approval/rejection is written to `audit_logs` with user_id, timestamp, and the full recommendation payload that was approved/rejected

---

## 8. Data Field → Rule Mapping (for Person B's synthetic data generator)

So the synthetic data actually reflects these rules instead of being random:
- Buyers should have a `payment_reliability` score that **correlates** with their historical `payment_date - due_date` deltas (reliable buyers should mostly show up as on-time in the generated payment history)
- ~15–20% of invoices should be "late" in the synthetic set (avoid extreme class imbalance for v1 — can add more imbalance later once baseline model works, per doc Section 27 imbalance note)
- Distribute buyers roughly: 40% Tier-A, 40% Tier-B, 20% Tier-C, so all three tiers are testable in the optimizer

---

## Decisions Log (finalized Aug 13–14, 2026)

**Q1 — Gross invoice amount or net margin for discount cost?**
**Decision: gross amount.** Net margin would need real COGS data we don't have; estimating it synthetically adds noise without adding credibility. Documented as a stated simplification in the README, not hidden.

**Q2 — Fixed or scaling weekly discount budget?**
**Decision: scaling**, per the formula in Section 5. A fixed ₹50,000 figure breaks the moment dataset size changes — it'd look absurdly generous on a small synthetic set and absurdly stingy on a larger one. Tying it to 1.5% of open invoice value keeps the number meaningful regardless of dataset scale, with a floor/ceiling so demo output stays legible.

**Q3 — Per-buyer discount frequency cap?**
**Decision: yes, 1 offer per buyer per rolling 14 days.** Without this, the optimizer could re-offer the same buyer every week, which (a) looks unrealistic in a demo and (b) undermines the core pitch that this system is smarter than blanket discounting.

These are now locked. If real project context later shows a decision was wrong (e.g. actual policy docs specify a different budget rule), update this file and flag the change to the other person before touching schema or optimizer code that depends on it.