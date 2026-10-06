from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Float, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class ModelPrediction(Base):
    __tablename__ = "model_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    invoice_id = Column(BigInteger, ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True)
    model_name = Column(String(100), default="payment_delay_predictor", nullable=False)
    model_version = Column(String(50), default="v1.0", nullable=False)
    late_probability = Column(Float, nullable=False)
    predicted_days_late = Column(Integer, nullable=True)
    predicted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("late_probability >= 0.0 AND late_probability <= 1.0", name="ck_model_predictions_late_prob"),
    )

    # Relationships
    invoice = relationship("Invoice", back_populates="model_predictions")
