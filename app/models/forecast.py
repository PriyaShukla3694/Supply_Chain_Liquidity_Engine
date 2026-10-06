from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, Float, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True, index=True)
    forecast_date = Column(Date, nullable=False, index=True)
    horizon_days = Column(Integer, nullable=False, index=True)
    expected_inflow = Column(Numeric(14, 2), nullable=False, default=0.00)
    expected_outflow = Column(Numeric(14, 2), nullable=False, default=0.00)
    net_liquidity = Column(Numeric(14, 2), nullable=False, default=0.00)
    liquidity_gap = Column(Numeric(14, 2), nullable=False, default=0.00)
    status = Column(String(50), default="HEALTHY", nullable=False, index=True)
    confidence_score = Column(Float, nullable=True)
    model_version = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('HEALTHY', 'WATCH', 'URGENT')", name="ck_forecasts_status"),
    )

    # Relationships
    company = relationship("Company", back_populates="forecasts")
