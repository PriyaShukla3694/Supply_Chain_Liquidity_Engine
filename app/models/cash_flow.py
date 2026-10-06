from sqlalchemy import Column, Integer, Date, DateTime, Numeric, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class CashFlow(Base):
    __tablename__ = "cash_flows"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True, index=True)
    date = Column(Date, nullable=False, index=True)
    inflow_actual = Column(Numeric(14, 2), nullable=False, default=0.00)
    outflow_actual = Column(Numeric(14, 2), nullable=False, default=0.00)
    net_cash_flow = Column(Numeric(14, 2), nullable=False, default=0.00)
    opening_balance = Column(Numeric(14, 2), nullable=False, default=0.00)
    closing_balance = Column(Numeric(14, 2), nullable=False, default=0.00)
    outstanding_receivables = Column(Numeric(14, 2), nullable=False, default=0.00)
    min_cash_buffer = Column(Numeric(14, 2), nullable=False, default=0.00)
    liquidity_gap = Column(Numeric(14, 2), nullable=False, default=0.00)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "date", name="uq_cash_flows_company_date"),
    )

    # Relationships
    company = relationship("Company", back_populates="cash_flows")
