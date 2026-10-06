from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    users = relationship("User", back_populates="company")
    suppliers = relationship("Supplier", back_populates="company")
    documents = relationship("Document", back_populates="company")
    cash_flows = relationship("CashFlow", back_populates="company")
    forecasts = relationship("Forecast", back_populates="company")