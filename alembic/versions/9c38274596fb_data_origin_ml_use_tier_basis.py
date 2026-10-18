"""data_origin_ml_use_tier_basis

Revision ID: 9c38274596fb
Revises: 6e6c4f5de99d
Create Date: 2026-10-08 06:10:22.229592

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '9c38274596fb'
down_revision: Union[str, Sequence[str], None] = '6e6c4f5de99d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add data_origin, ml_use_allowed, invoice_amount to discount_offers, and tier_basis to buyers and risk_scores."""
    # discount_offers
    op.add_column('discount_offers', sa.Column('data_origin', sa.String(length=100), nullable=True))
    op.add_column('discount_offers', sa.Column('ml_use_allowed', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('discount_offers', sa.Column('invoice_amount', sa.Numeric(precision=14, scale=2), nullable=True))

    # buyers
    op.add_column('buyers', sa.Column('tier_basis', sa.String(length=30), nullable=True))

    # risk_scores
    op.add_column('risk_scores', sa.Column('tier_basis', sa.String(length=30), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('risk_scores', 'tier_basis')
    op.drop_column('buyers', 'tier_basis')
    op.drop_column('discount_offers', 'invoice_amount')
    op.drop_column('discount_offers', 'ml_use_allowed')
    op.drop_column('discount_offers', 'data_origin')

