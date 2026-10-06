from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from app.db.session import Base


class BusinessRule(Base):
    __tablename__ = "business_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_key = Column(String(100), unique=True, index=True, nullable=False)
    rule_value = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    description = Column(String, nullable=True)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
