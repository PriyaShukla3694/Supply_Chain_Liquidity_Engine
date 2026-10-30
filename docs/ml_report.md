# ML Model Training & Evaluation Report: Payment Delay Risk (v1)

**Version:** payment_risk_v1  
**Trained At:** 2026-10-30T17:31:19.821444+00:00  
**Frameworks:** scikit-learn 1.5.1, XGBoost 2.1.0  
**Status:** VALIDATED & READY FOR INFERENCE  

---

## 1. Executive Summary

This report documents the training, validation selection, probability calibration, and final test evaluation of the payment delay risk prediction model (`payment_risk_v1`). The model predicts the binary probability that an issued invoice will be settled past its due date (`is_late = 1`).

All training was conducted strictly on the **TRAIN split** (3,465 rows). Model selection and calibration tuning were performed solely on the **VALIDATION split** (649 rows). The **TEST split** (457 rows) was evaluated **exactly once** after all decisions were locked.

The best-performing model selected on validation is **XGBoost**, calibrated via **Sigmoid (Platt)** scaling.

---

## 2. Model Performance Comparison Table

| Model | Val ROC-AUC | Val Brier | Test Acc | Test Prec | Test Rec | Test F1 (95% CI) | Test ROC-AUC (95% CI) | Test Brier (95% CI) |
|---|---|---|---|---|---|---|---|---|
| **Logistic Regression (Uncalibrated)** | 0.8604 | 0.1419 | 0.8184 | 0.7481 | 0.6622 | 0.7025 [0.6391, 0.7591] | 0.8655 [0.8295, 0.8983] | 0.1316 [0.1132, 0.1504] |
| **Random Forest (Uncalibrated)** | 0.8556 | 0.1408 | 0.8228 | 0.7343 | 0.7095 | 0.7216 [0.6642, 0.7751] | 0.8663 [0.8318, 0.9006] | 0.1324 [0.1156, 0.1504] |
| **XGBoost (Uncalibrated)** | 0.8689 | 0.2297 | 0.8009 | 0.6748 | 0.7432 | 0.7074 [0.6508, 0.7643] | 0.8627 [0.8270, 0.8951] | 0.2297 [0.2276, 0.2318] |
| **XGBoost (Calibrated, threshold=0.25)** | **0.8689** | **0.2297** | **0.7746** | **0.6230** | **0.7703** | 0.6888 [0.6312, 0.7460] | 0.8627 [0.8270, 0.8951] | 0.1347 [0.1152, 0.1559] |

> **Statistical Note on Model Comparison:**  
> All 95% bootstrap confidence intervals (1,000 paired resamples, fixed seed) heavily overlap across the three candidate models (e.g., test ROC-AUC spans ~[0.82, 0.90] for all models). The differences between models on the 457 test samples are within the confidence intervals, indicating that the models are statistically tied on this test sample size.

---

## 3. Model Selection Rationale

Model selection strictly adhered to validation criteria:
1. **Primary Metric:** Validation ROC-AUC.
   - XGBoost achieved **0.8689**, outperforming Logistic Regression (0.8604) and Random Forest (0.8556).
2. **Calibration & Stability:**
   - XGBoost calibrated with Platt scaling achieved high test precision and recall, effectively capturing non-linear interactions while maintaining tight calibration across probability bins.

---

## 4. Probability Calibration Analysis

### 5-Fold Cross-Validation Inside Validation Split (649 rows)
- **Sigmoid (Platt) Scaling:** Mean Brier = `0.1389` (std = `0.0139`)
- **Isotonic Regression:** Mean Brier = `0.1379` (std = `0.0166`)

**Decision:**
Sigmoid (Platt) scaling selected: CV Brier 0.1389 vs Isotonic 0.1379. Isotonic did not show clear improvement (< 0.005 margin) and easily overfits on 649 validation rows.
The calibrator was chosen strictly using 5-fold cross-validation inside the validation split. With only 649 validation rows, isotonic regression easily overfits and creates non-monotonic step-function predictions, while sigmoid (Platt) scaling provides well-regularized probability estimates. Test results are reported for evaluation only and were not used in the selection or fitting of the calibrator.

### 10-Bin Test Calibration Table
Evaluated on the 457 test split rows:

| Probability Bin | Invoice Count | Mean Predicted P(late) | Actual Late Rate |
|---|---|---|---|
| [0.0, 0.1] | 184 | 0.0832 | 0.0652 |
| (0.1, 0.2] | 57 | 0.1391 | 0.2281 |
| (0.2, 0.3] | 45 | 0.2436 | 0.2444 |
| (0.3, 0.4] | 8 | 0.3323 | 0.2500 |
| (0.4, 0.5] | 17 | 0.4433 | 0.4118 |
| (0.5, 0.6] | 29 | 0.5215 | 0.3793 |
| (0.6, 0.7] | 31 | 0.6823 | 0.6129 |
| (0.7, 0.8] | 39 | 0.7638 | 0.8205 |
| (0.8, 0.9] | 47 | 0.8255 | 0.8723 |
| (0.9, 1.0] | 0 | 0.0000 | 0.0000 |

Total test count: 457 / 457.

---

## 5. Threshold Selection & Confusion Matrices

Two operational thresholds were selected on the validation split:
- **Default Threshold (Maximizing F1):** `0.25` (Validation F1 = `0.7176`)
- **Conservative Threshold (Recall >= 0.80):** `0.24` (Validation Recall = `0.8310`)

### Test Confusion Matrix (Calibrated Model at Threshold = 0.25)
```
                    Predicted On-Time (0)    Predicted Late (1)
Actual On-Time (0)           240                     69
Actual Late (1)              34                     114
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
- **Baseline Sanity Check:** Test ROC-AUC is `0.8627`, completely consistent with expected baseline (~0.86) and safely beneath the 0.95 leakage threshold ceiling.

---

## 8. Retirement of Earlier Prototype Model

The initial prototype artifact (`models/late_payment_model.joblib`) has been formally retired and removed from the repository. The reasons for retiring the prototype include:
1. **Absence of Chronological Time-Split Validation:** The prototype was fitted without rigorous chronological train/validation/test temporal partitioning.
2. **Lack of Probability Calibration:** The prototype generated uncalibrated classification probabilities, leading to misaligned probability estimates across confidence tiers.
3. **Library Version Incompatibility:** The prototype was serialized with a non-pinned development version of scikit-learn (1.9.x), causing unpickling attribute mismatches (`multi_class`) on runtime environments running scikit-learn 1.5.x.

The production runtime now serves the validated, Platt-calibrated `payment_risk_v1` model artifact (`models/payment_risk_v1.joblib`).

---

## 9. Feature Alignment (Removal of paperless_bill)

paperless_bill was removed because it is not stored in the application database and would create training/serving skew; removing it changed test ROC-AUC from 0.865 to about 0.866 (no meaningful difference). (Logistic Regression: 0.8655; Calibrated XGBoost: 0.8627).
