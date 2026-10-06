from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    buyer_id = Column(String(50), ForeignKey("buyers.buyer_id", ondelete="CASCADE"), nullable=False, index=True)
    payment_reliability = Column(Numeric(5, 2), nullable=False)
    financial_risk = Column(Numeric(5, 2), nullable=False)
    liquidity_risk = Column(Numeric(5, 2), nullable=False)
    overall_risk = Column(Numeric(5, 2), nullable=False)
    tier = Column(String(20), nullable=True, index=True)  # 'A', 'B', 'C' or NULL
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    model_version = Column(String(50), default="v1.0", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("payment_reliability >= 0 AND payment_reliability <= 100", name="ck_risk_scores_payment_reliability"),
        CheckConstraint("financial_risk >= 0 AND financial_risk <= 100", name="ck_risk_scores_financial_risk"),
        CheckConstraint("liquidity_risk >= 0 AND liquidity_risk <= 100", name="ck_risk_scores_liquidity_risk"),
        CheckConstraint("overall_risk >= 0 AND overall_risk <= 100", name="ck_risk_scores_overall_risk"),
        CheckConstraint("tier IS NULL OR tier IN ('A', 'B', 'C')", name="ck_risk_scores_tier"),
    )

    # Relationships
    buyer = relationship("Buyer", back_populates="risk_scores")
