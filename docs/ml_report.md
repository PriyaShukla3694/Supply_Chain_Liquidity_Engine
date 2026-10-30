# ML Model Training & Evaluation Report: Payment Delay Risk (v1)

**Version:** payment_risk_v1  
**Trained At:** 2026-10-30T00:47:18.042750+00:00  
**Frameworks:** scikit-learn 1.5.1, XGBoost 2.1.0  
**Status:** VALIDATED & READY FOR INFERENCE  

---

## 1. Executive Summary

This report documents the training, validation selection, probability calibration, and final test evaluation of the payment delay risk prediction model (`payment_risk_v1`). The model predicts the binary probability that an issued invoice will be settled past its due date (`is_late = 1`).

All training was conducted strictly on the **TRAIN split** (3,465 rows). Model selection and calibration tuning were performed solely on the **VALIDATION split** (649 rows). The **TEST split** (457 rows) was evaluated **exactly once** after all decisions were locked.

The best-performing model selected on validation is **LogisticRegression**, calibrated via **Sigmoid (Platt)** scaling.

---

## 2. Model Performance Comparison Table

| Model | Val ROC-AUC | Val Brier | Test Acc | Test Prec | Test Rec | Test F1 (95% CI) | Test ROC-AUC (95% CI) | Test Brier (95% CI) |
|---|---|---|---|---|---|---|---|---|
| **Logistic Regression (Uncalibrated)** | 0.8684 | 0.1401 | 0.8096 | 0.7075 | 0.7027 | 0.7051 [0.6449, 0.7613] | 0.8650 [0.8303, 0.8969] | 0.1354 [0.1177, 0.1544] |
| **Random Forest (Uncalibrated)** | 0.8557 | 0.1402 | 0.8074 | 0.7113 | 0.6824 | 0.6966 [0.6360, 0.7518] | 0.8670 [0.8311, 0.9005] | 0.1326 [0.1163, 0.1499] |
| **XGBoost (Uncalibrated)** | 0.8642 | 0.1428 | 0.7965 | 0.6708 | 0.7297 | 0.6990 [0.6413, 0.7550] | 0.8650 [0.8268, 0.8989] | 0.1411 [0.1263, 0.1569] |
| **LogisticRegression (Calibrated, threshold=0.25)** | **0.8684** | **0.1401** | **0.7571** | **0.5894** | **0.8243** | 0.6873 [0.6312, 0.7397] | 0.8650 [0.8303, 0.8969] | 0.1322 [0.1141, 0.1506] |

> **Statistical Note on Model Comparison:**  
> All 95% bootstrap confidence intervals (1,000 paired resamples, fixed seed) heavily overlap across the three candidate models (e.g., test ROC-AUC spans ~[0.82, 0.90] for all models). The differences between models on the 457 test samples are within the confidence intervals, indicating that the models are statistically tied on this test sample size.

---

## 3. Model Selection Rationale

Model selection strictly adhered to validation criteria:
1. **Primary Metric:** Validation ROC-AUC.
   - Logistic Regression achieved **0.8684**, outperforming XGBoost (0.8642) and Random Forest (0.8557).
2. **Tie-Break Metric:** Validation Brier score (lower is better).
   - Logistic Regression produced the lowest validation Brier score (**0.1401** vs RF 0.1402 and XGB 0.1428).
3. **Generalization & Interpretability:**
   - The linear model with median imputation and standard scaling demonstrated superior stability across time-aware splits with no sign of tree-depth overfitting on buyer history lag features.

---

## 4. Probability Calibration Analysis

### 5-Fold Cross-Validation Inside Validation Split (649 rows)
- **Sigmoid (Platt) Scaling:** Mean Brier = `0.1365` (std = `0.0079`)
- **Isotonic Regression:** Mean Brier = `0.1351` (std = `0.0085`)

**Decision:**
Sigmoid (Platt) scaling selected: CV Brier 0.1365 vs Isotonic 0.1351. Isotonic did not show clear improvement (< 0.005 margin) and easily overfits on 649 validation rows.
The calibrator was chosen strictly using 5-fold cross-validation inside the validation split. With only 649 validation rows, isotonic regression easily overfits and creates non-monotonic step-function predictions, while sigmoid (Platt) scaling provides well-regularized probability estimates. Test results are reported for evaluation only and were not used in the selection or fitting of the calibrator.

### 10-Bin Test Calibration Table
Evaluated on the 457 test split rows:

| Probability Bin | Invoice Count | Mean Predicted P(late) | Actual Late Rate |
|---|---|---|---|
| [0.0, 0.1] | 136 | 0.0675 | 0.0368 |
| (0.1, 0.2] | 87 | 0.1384 | 0.1609 |
| (0.2, 0.3] | 46 | 0.2437 | 0.2826 |
| (0.3, 0.4] | 44 | 0.3436 | 0.2727 |
| (0.4, 0.5] | 28 | 0.4462 | 0.3571 |
| (0.5, 0.6] | 16 | 0.5470 | 0.6250 |
| (0.6, 0.7] | 22 | 0.6499 | 0.9091 |
| (0.7, 0.8] | 32 | 0.7573 | 0.7812 |
| (0.8, 0.9] | 31 | 0.8501 | 0.8387 |
| (0.9, 1.0] | 15 | 0.9397 | 0.8667 |

Total test count: 457 / 457.

---

## 5. Threshold Selection & Confusion Matrices

Two operational thresholds were selected on the validation split:
- **Default Threshold (Maximizing F1):** `0.25` (Validation F1 = `0.7163`)
- **Conservative Threshold (Recall >= 0.80):** `0.27` (Validation Recall = `0.8028`)

### Test Confusion Matrix (Calibrated Model at Threshold = 0.25)
```
                    Predicted On-Time (0)    Predicted Late (1)
Actual On-Time (0)           224                     85
Actual Late (1)              26                     122
```
- Total test instances: 457 (must equal 457).

---

## 6. Model Limitations & Operational Scope

1. **All Test Buyers Appear in Training:** All buyers in the test split also appear in the training split. The model is specifically tuned for returning-buyer scoring; new buyers with fewer than 5 resolved invoices must be handled exclusively by the business cold-start rule (provisional Tier B, never Tier A).
2. **Models Are Statistically Tied on 457 Rows:** Given the test set sample size of 457 rows, the 95% bootstrap confidence intervals for ROC-AUC, F1, and Brier overlap across Logistic Regression, Random Forest, and XGBoost. The models are statistically tied on this test sample size.
3. **Sparse Calibration Samples at High Probabilities:** Probabilities beyond 0.6 have relatively few samples per bin (e.g., bins (0.5, 0.6] and (0.9, 1.0] have 16 and 15 observations respectively). Probability calibration estimates in this upper region carry wider variance.
4. **Net-30 Terms Only:** The dataset exclusively contains Net-30 invoice agreements. Invoices under different settlement terms (e.g., Net-15, Net-60) should not be scored with this model version without recalibration.
5. **~34% Late Rate Class Distribution:** The historical dataset has ~34.7% late invoices in train, 32.8% in validation, and 32.4% in test. While class imbalance was handled via balanced weighting and probability calibration, severe macroeconomic shifts in base delay rates will require threshold adjustments.
6. **Small Test Set:** The test split consists of 457 rows. Metric confidence intervals should be monitored in production.
7. **Hybrid Real + Synthetic Data:** The dataset is derived from real enterprise invoice structures augmented with synthetic buyer profiles and payment timelines.
8. **Simulated Offer History Excluded:** Early payment discount offer histories were deliberately excluded from training inputs to prevent feedback loops where past discount acceptance masks latent credit risk.
9. **Buyer History Features from Same Dataset:** Buyer historical performance metrics (`buyer_hist_*`) were computed from historical chronological settlement records within the same dataset.

---

## 7. Anti-Leakage Compliance & Sanity Verification

- **Feature Disjointness:** All features in `FEATURES` strictly exclude post-issuance fields (`payment_date`, `settled_date`, `days_to_settle`, `days_late`, `delay_bucket`, `invoice_status`, `disputed`, `buyer_hist_dispute_rate`).
- **Baseline Sanity Check:** Test ROC-AUC is `0.8650`, completely consistent with expected baseline (~0.86) and safely beneath the 0.95 leakage threshold ceiling.
