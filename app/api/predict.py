from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.buyer import Buyer
from app.models.invoice import Invoice
from app.models.risk_score import RiskScore
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.prediction import (
    BatchPaymentRiskRequest,
    BatchPaymentRiskResponse,
    CustomerRiskResponse,
    LatePaymentPredictionResponseExtended,
)
from app.services.prediction import (
    build_features_from_invoice,
    predict_late_payment_features,
)

router = APIRouter(prefix="/predict", tags=["Prediction"])


@router.get(
    "/payment-risk/{invoice_id}",
    response_model=LatePaymentPredictionResponseExtended,
    summary="Predict Payment Delay Risk for an Invoice",
    description="Builds features from the database as of invoice date and returns payment risk prediction.",
)
def predict_payment_risk_endpoint(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager", "analyst")
    ),
):
    invoice = (
        db.query(Invoice)
        .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
        .filter(
            Invoice.invoice_id == invoice_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice '{invoice_id}' not found",
        )

    features = build_features_from_invoice(invoice_id=invoice_id, db=db)
    return predict_late_payment_features(invoice_id=invoice_id, features=features, db=db)


@router.post(
    "/payment-risk/batch",
    response_model=BatchPaymentRiskResponse,
    summary="Batch Predict Payment Risk for Invoices",
    description="Predict payment risk for up to 200 invoice IDs.",
)
def batch_predict_payment_risk_endpoint(
    request: BatchPaymentRiskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager", "analyst")
    ),
):
    if len(request.invoice_ids) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Batch size exceeds maximum limit of 200 invoice IDs",
        )

    predictions: List[LatePaymentPredictionResponseExtended] = []
    for inv_id in request.invoice_ids:
        invoice = (
            db.query(Invoice)
            .join(Supplier, Invoice.supplier_id == Supplier.supplier_id)
            .filter(
                Invoice.invoice_id == inv_id,
                Supplier.company_id == current_user.company_id,
            )
            .first()
        )
        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice '{inv_id}' not found",
            )

        features = build_features_from_invoice(invoice_id=inv_id, db=db)
        pred = predict_late_payment_features(invoice_id=inv_id, features=features, db=db)
        predictions.append(pred)

    return BatchPaymentRiskResponse(predictions=predictions, count=len(predictions))


@router.get(
    "/customer-risk/{buyer_id}",
    response_model=CustomerRiskResponse,
    summary="Get Buyer Customer Risk Score",
    description="Reads persisted buyer risk scores: overall, sub-scores, tier, tier-basis, and as-of date.",
)
def get_customer_risk_endpoint(
    buyer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("admin", "finance_manager", "analyst")
    ),
):
    buyer = (
        db.query(Buyer)
        .join(Supplier, Buyer.primary_supplier_id == Supplier.supplier_id)
        .filter(
            Buyer.buyer_id == buyer_id,
            Supplier.company_id == current_user.company_id,
        )
        .first()
    )
    if buyer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Buyer '{buyer_id}' not found",
        )

    risk_score = (
        db.query(RiskScore)
        .filter(RiskScore.buyer_id == buyer_id)
        .order_by(RiskScore.computed_at.desc())
        .first()
    )

    if risk_score is None:
        if buyer.tier is not None or buyer.tier_basis is not None:
            return CustomerRiskResponse(
                buyer_id=buyer.buyer_id,
                overall_risk=0.0,
                payment_reliability=0.0,
                financial_risk=0.0,
                liquidity_risk=0.0,
                tier=buyer.tier,
                tier_basis=buyer.tier_basis,
                as_of_date=buyer.last_invoice_date.isoformat() if buyer.last_invoice_date else None,
                model_version="rules_v1",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk score for buyer '{buyer_id}' not found",
        )

    as_of_str = (
        risk_score.computed_at.date().isoformat()
        if risk_score.computed_at
        else None
    )

    return CustomerRiskResponse(
        buyer_id=risk_score.buyer_id,
        overall_risk=float(risk_score.overall_risk),
        payment_reliability=float(risk_score.payment_reliability),
        financial_risk=float(risk_score.financial_risk),
        liquidity_risk=float(risk_score.liquidity_risk),
        tier=risk_score.tier,
        tier_basis=risk_score.tier_basis,
        as_of_date=as_of_str,
        model_version=risk_score.model_version,
    )

