from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="analyst", index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'finance_manager', 'analyst')", name="ck_users_role"),
    )

    # Relationships
    company = relationship("Company", back_populates="users")
    approved_discount_offers = relationship(
        "DiscountOffer",
        back_populates="approved_by_user",
        foreign_keys="DiscountOffer.approved_by"
    )
    uploaded_documents = relationship(
        "Document",
        back_populates="uploader",
        foreign_keys="Document.uploaded_by"
    )
    audit_logs = relationship("AuditLog", back_populates="user")
