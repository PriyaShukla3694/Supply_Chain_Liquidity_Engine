from sqlalchemy import Column, BigInteger, Integer, String, Boolean, Date, DateTime, Numeric, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=False, index=True)
    buyer_id = Column(String(50), ForeignKey("buyers.buyer_id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(String(50), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False, index=True)
    payment_terms_days = Column(Integer, nullable=False, default=30)
    invoice_amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(10), default="INR", nullable=False)
    disputed = Column(Boolean, default=False, nullable=False, index=True)
    invoice_status = Column(String(50), default="open", nullable=False, index=True)  # open / settled
    settled_date = Column(Date, nullable=True)
    days_late = Column(Integer, nullable=True)
    is_late = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        CheckConstraint("invoice_status IN ('open', 'settled')", name="ck_invoices_status"),
    )

    # Relationships
    buyer = relationship("Buyer", back_populates="invoices")
    supplier = relationship("Supplier", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice")
    discount_offers = relationship("DiscountOffer", back_populates="invoice")
    model_predictions = relationship("ModelPrediction", back_populates="invoice")
