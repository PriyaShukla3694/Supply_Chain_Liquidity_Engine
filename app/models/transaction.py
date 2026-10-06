from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Numeric, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, index=True)
    payment_id = Column(BigInteger, ForeignKey("payments.payment_id", ondelete="SET NULL"), nullable=True, index=True)
    transaction_type = Column(String(50), nullable=False, index=True)  # credit / debit
    amount = Column(Numeric(14, 2), nullable=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False, index=True)
    currency = Column(String(10), default="INR", nullable=False)
    account_number = Column(String(100), nullable=True)
    description = Column(String(255), nullable=True)
    status = Column(String(50), default="settled", nullable=False, index=True)  # settled / pending / failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        CheckConstraint("transaction_type IN ('credit', 'debit')", name="ck_transactions_type"),
        CheckConstraint("status IN ('settled', 'pending', 'failed')", name="ck_transactions_status"),
    )

    # Relationships
    payment = relationship("Payment", back_populates="transactions")
