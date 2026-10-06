from sqlalchemy import Column, BigInteger, Integer, String, Date, DateTime, Numeric, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Payment(Base):
    __tablename__ = "payments"

    payment_id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, index=True)
    invoice_id = Column(BigInteger, ForeignKey("invoices.invoice_id", ondelete="RESTRICT"), nullable=False, index=True)
    payment_date = Column(Date, nullable=False, index=True)
    payment_amount = Column(Numeric(14, 2), nullable=False)
    payment_method = Column(String(50), nullable=True)
    reference_number = Column(String(100), nullable=True)
    status = Column(String(50), default="completed", nullable=False, index=True)
    discount_applied = Column(Numeric(14, 2), default=0.00, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('completed', 'pending', 'failed', 'refunded')", name="ck_payments_status"),
    )

    # Relationships
    invoice = relationship("Invoice", back_populates="payments")
    transactions = relationship("Transaction", back_populates="payment")
