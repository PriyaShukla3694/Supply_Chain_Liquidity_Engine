from sqlalchemy import Column, BigInteger, String, Boolean, Integer, Date, DateTime, Numeric, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class DiscountOffer(Base):
    __tablename__ = "discount_offers"

    offer_id = Column(String(100), primary_key=True, index=True)
    invoice_id = Column(BigInteger, ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_id = Column(String(50), ForeignKey("buyers.buyer_id", ondelete="CASCADE"), nullable=False, index=True)
    offer_date = Column(Date, nullable=False, index=True)
    deadline_date = Column(Date, nullable=False, index=True)
    offered_rate_pct = Column(Numeric(6, 4), nullable=False)
    discount_amount = Column(Numeric(14, 2), nullable=False)
    net_payable_if_accepted = Column(Numeric(14, 2), nullable=False)
    days_accelerated = Column(Integer, nullable=False)
    status = Column(String(50), default="recommended", nullable=False, index=True)
    recommended_by = Column(String(100), default="optimizer", nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    requires_approval = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('recommended', 'offered', 'accepted', 'declined', 'expired', 'rejected')",
            name="ck_discount_offers_status"
        ),
    )

    # Relationships
    invoice = relationship("Invoice", back_populates="discount_offers")
    buyer = relationship("Buyer", back_populates="discount_offers")
    approved_by_user = relationship(
        "User",
        back_populates="approved_discount_offers",
        foreign_keys=[approved_by]
    )
