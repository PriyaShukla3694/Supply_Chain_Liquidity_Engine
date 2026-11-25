"""Tests for ML payment risk model training pipeline, artifact integrity, and determinism."""

from pathlib import Path
import joblib
import numpy as np
import pytest

from app.ml.features import FORBIDDEN, assert_no_leakage, load_training_frame
from scripts.train_payment_model import (
    FEATURES,
    train_payment_risk_model,
)

ARTIFACT_PATH = Path("models/payment_risk_v1.joblib")


@pytest.mark.unit
def test_saved_feature_list_no_leakage():
    """Verify that the saved model feature list contains no forbidden features and passes assert_no_leakage."""
    if ARTIFACT_PATH.exists():
        try:
            artifact = joblib.load(ARTIFACT_PATH)
            features = artifact["features"]
        except Exception:
            features = FEATURES
    else:
        features = FEATURES

    assert_no_leakage(features)

    # Disjointness check
    forbidden_set = set(FORBIDDEN)
    for feat in features:
        assert feat not in forbidden_set, f"Forbidden feature '{feat}' detected in saved features"


@pytest.mark.unit
def test_artifact_inference_predict_proba():
    """Verify that if the model artifact exists, it loads and predict_proba returns values in [0, 1] for 5 validation rows."""
    if not ARTIFACT_PATH.exists():
        pytest.skip("Model artifact 'models/payment_risk_v1.joblib' does not exist; skipping artifact test.")

    artifact = joblib.load(ARTIFACT_PATH)

    import sklearn
    if artifact.get("sklearn_version") and artifact.get("sklearn_version").split(".")[:2] != sklearn.__version__.split(".")[:2]:
        pytest.skip(
            f"Artifact was serialized with sklearn {artifact.get('sklearn_version')} "
            f"which is incompatible with current environment sklearn {sklearn.__version__}."
        )

    required_keys = {
        "model",
        "calibrator",
        "threshold",
        "threshold_recall80",
        "features",
        "version",
        "trained_at",
        "sklearn_version",
        "xgboost_version",
    }
    assert required_keys.issubset(artifact.keys()), f"Missing keys in artifact: {required_keys - set(artifact.keys())}"

    splits = load_training_frame()
    sample_rows = splits.validation[artifact["features"]].head(5)
    assert len(sample_rows) == 5, f"Expected 5 validation sample rows, got {len(sample_rows)}"

    # Test calibrator predict_proba
    calibrator = artifact["calibrator"]
    cal_probs = calibrator.predict_proba(sample_rows)
    assert cal_probs.shape == (5, 2), f"Expected shape (5, 2), got {cal_probs.shape}"
    assert np.all(cal_probs >= 0.0) and np.all(cal_probs <= 1.0), "Calibrator probabilities out of [0, 1] bounds"
    assert np.allclose(cal_probs.sum(axis=1), 1.0), "Calibrator class probabilities do not sum to 1.0"

    # Test base model predict_proba
    base_model = artifact["model"]
    base_probs = base_model.predict_proba(sample_rows)
    assert base_probs.shape == (5, 2), f"Expected shape (5, 2), got {base_probs.shape}"
    assert np.all(base_probs >= 0.0) and np.all(base_probs <= 1.0), "Base model probabilities out of [0, 1] bounds"
    assert np.allclose(base_probs.sum(axis=1), 1.0), "Base model class probabilities do not sum to 1.0"

    # Verify thresholds are valid probability cutoffs
    assert 0.0 < artifact["threshold"] < 1.0, f"Invalid threshold {artifact['threshold']}"
    assert 0.0 < artifact["threshold_recall80"] < 1.0, f"Invalid recall-80 threshold {artifact['threshold_recall80']}"


@pytest.mark.unit
def test_training_determinism_identical_roc_auc():
    """Verify that running the training function twice with the same seed yields identical validation ROC-AUC."""
    res1 = train_payment_risk_model(random_state=42, save_artifacts=False)
    res2 = train_payment_risk_model(random_state=42, save_artifacts=False)

    for model_name in ["LogisticRegression", "RandomForest", "XGBoost"]:
        auc1 = res1["validation_metrics"][model_name]["roc_auc"]
        auc2 = res2["validation_metrics"][model_name]["roc_auc"]
        assert auc1 == auc2, (
            f"Non-deterministic validation ROC-AUC for {model_name}: {auc1} vs {auc2}"
        )

        brier1 = res1["validation_metrics"][model_name]["brier"]
        brier2 = res2["validation_metrics"][model_name]["brier"]
        assert brier1 == brier2, (
            f"Non-deterministic validation Brier for {model_name}: {brier1} vs {brier2}"
        )

    assert res1["selected_model"] == res2["selected_model"]
    assert res1["selected_calibration_method"] == res2["selected_calibration_method"]
    assert res1["threshold"] == res2["threshold"]
    assert res1["threshold_recall80"] == res2["threshold_recall80"]

