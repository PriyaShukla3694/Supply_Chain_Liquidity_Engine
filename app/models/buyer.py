from sqlalchemy import Column, String, Boolean, Date, DateTime, Numeric, Float, ForeignKey, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Buyer(Base):
    __tablename__ = "buyers"

    buyer_id = Column(String(50), primary_key=True, index=True)
    country_code = Column(String(10), nullable=True)
    primary_supplier_id = Column(String(50), ForeignKey("suppliers.supplier_id", ondelete="SET NULL"), nullable=True, index=True)
    behavioural_segment = Column(String(100), nullable=True)
    tier = Column(String(20), nullable=True, index=True)  # e.g. 'Tier-A', 'Tier-B', 'Tier-C' or 'A', 'B', 'C'
    credit_limit = Column(Numeric(14, 2), nullable=True, default=0.00)
    discount_responsiveness = Column(Float, nullable=True)
    blacklisted = Column(Boolean, default=False, nullable=False, index=True)
    disputed_flag = Column(Boolean, default=False, nullable=False, index=True)
    first_invoice_date = Column(Date, nullable=True)
    last_invoice_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    # Relationships
    primary_supplier = relationship("Supplier", back_populates="primary_buyers")
    invoices = relationship("Invoice", back_populates="buyer")
    discount_offers = relationship("DiscountOffer", back_populates="buyer")
    risk_scores = relationship("RiskScore", back_populates="buyer")
