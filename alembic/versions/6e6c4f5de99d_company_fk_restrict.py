"""company_fk_restrict

Revision ID: 6e6c4f5de99d
Revises: cae90a36294f
Create Date: 2026-10-07 02:28:29.024618

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = '6e6c4f5de99d'
down_revision: Union[str, Sequence[str], None] = 'cae90a36294f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: change ON DELETE to RESTRICT for company_id foreign keys."""
    # cash_flows.company_id
    op.drop_constraint('cash_flows_company_id_fkey', 'cash_flows', type_='foreignkey')
    op.create_foreign_key('cash_flows_company_id_fkey', 'cash_flows', 'companies', ['company_id'], ['id'], ondelete='RESTRICT')

    # documents.company_id
    op.drop_constraint('documents_company_id_fkey', 'documents', type_='foreignkey')
    op.create_foreign_key('documents_company_id_fkey', 'documents', 'companies', ['company_id'], ['id'], ondelete='RESTRICT')

    # forecasts.company_id
    op.drop_constraint('forecasts_company_id_fkey', 'forecasts', type_='foreignkey')
    op.create_foreign_key('forecasts_company_id_fkey', 'forecasts', 'companies', ['company_id'], ['id'], ondelete='RESTRICT')

    # suppliers.company_id
    op.drop_constraint('suppliers_company_id_fkey', 'suppliers', type_='foreignkey')
    op.create_foreign_key('suppliers_company_id_fkey', 'suppliers', 'companies', ['company_id'], ['id'], ondelete='RESTRICT')

    # users.company_id
    op.drop_constraint('users_company_id_fkey', 'users', type_='foreignkey')
    op.create_foreign_key('users_company_id_fkey', 'users', 'companies', ['company_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    """Downgrade schema: restore previous foreign key ondelete behaviors."""
    op.drop_constraint('users_company_id_fkey', 'users', type_='foreignkey')
    op.create_foreign_key('users_company_id_fkey', 'users', 'companies', ['company_id'], ['id'], ondelete='SET NULL')

    op.drop_constraint('suppliers_company_id_fkey', 'suppliers', type_='foreignkey')
    op.create_foreign_key('suppliers_company_id_fkey', 'suppliers', 'companies', ['company_id'], ['id'], ondelete='SET NULL')

    op.drop_constraint('forecasts_company_id_fkey', 'forecasts', type_='foreignkey')
    op.create_foreign_key('forecasts_company_id_fkey', 'forecasts', 'companies', ['company_id'], ['id'], ondelete='SET NULL')

    op.drop_constraint('documents_company_id_fkey', 'documents', type_='foreignkey')
    op.create_foreign_key('documents_company_id_fkey', 'documents', 'companies', ['company_id'], ['id'], ondelete='CASCADE')

    op.drop_constraint('cash_flows_company_id_fkey', 'cash_flows', type_='foreignkey')
    op.create_foreign_key('cash_flows_company_id_fkey', 'cash_flows', 'companies', ['company_id'], ['id'], ondelete='SET NULL')
