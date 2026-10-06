"""fk_ondelete_restrict

Revision ID: cae90a36294f
Revises: d691f9752240
Create Date: 2026-10-07 02:19:07.311128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


# revision identifiers, used by Alembic.
revision: str = 'cae90a36294f'
down_revision: Union[str, Sequence[str], None] = 'd691f9752240'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: change ON DELETE to RESTRICT for financial/audit foreign keys."""
    # audit_logs.user_id
    op.drop_constraint('audit_logs_user_id_fkey', 'audit_logs', type_='foreignkey')
    op.create_foreign_key('audit_logs_user_id_fkey', 'audit_logs', 'users', ['user_id'], ['id'], ondelete='RESTRICT')

    # buyers.primary_supplier_id
    op.drop_constraint('buyers_primary_supplier_id_fkey', 'buyers', type_='foreignkey')
    op.create_foreign_key('buyers_primary_supplier_id_fkey', 'buyers', 'suppliers', ['primary_supplier_id'], ['supplier_id'], ondelete='RESTRICT')

    # discount_offers (buyer_id, invoice_id, approved_by)
    op.drop_constraint('discount_offers_buyer_id_fkey', 'discount_offers', type_='foreignkey')
    op.drop_constraint('discount_offers_invoice_id_fkey', 'discount_offers', type_='foreignkey')
    op.drop_constraint('discount_offers_approved_by_fkey', 'discount_offers', type_='foreignkey')
    op.create_foreign_key('discount_offers_buyer_id_fkey', 'discount_offers', 'buyers', ['buyer_id'], ['buyer_id'], ondelete='RESTRICT')
    op.create_foreign_key('discount_offers_invoice_id_fkey', 'discount_offers', 'invoices', ['invoice_id'], ['invoice_id'], ondelete='RESTRICT')
    op.create_foreign_key('discount_offers_approved_by_fkey', 'discount_offers', 'users', ['approved_by'], ['id'], ondelete='RESTRICT')

    # invoices (buyer_id, supplier_id)
    op.drop_constraint('invoices_buyer_id_fkey', 'invoices', type_='foreignkey')
    op.drop_constraint('invoices_supplier_id_fkey', 'invoices', type_='foreignkey')
    op.create_foreign_key('invoices_buyer_id_fkey', 'invoices', 'buyers', ['buyer_id'], ['buyer_id'], ondelete='RESTRICT')
    op.create_foreign_key('invoices_supplier_id_fkey', 'invoices', 'suppliers', ['supplier_id'], ['supplier_id'], ondelete='RESTRICT')

    # model_predictions.invoice_id
    op.drop_constraint('model_predictions_invoice_id_fkey', 'model_predictions', type_='foreignkey')
    op.create_foreign_key('model_predictions_invoice_id_fkey', 'model_predictions', 'invoices', ['invoice_id'], ['invoice_id'], ondelete='RESTRICT')

    # payments.invoice_id
    op.drop_constraint('payments_invoice_id_fkey', 'payments', type_='foreignkey')
    op.create_foreign_key('payments_invoice_id_fkey', 'payments', 'invoices', ['invoice_id'], ['invoice_id'], ondelete='RESTRICT')

    # risk_scores.buyer_id
    op.drop_constraint('risk_scores_buyer_id_fkey', 'risk_scores', type_='foreignkey')
    op.create_foreign_key('risk_scores_buyer_id_fkey', 'risk_scores', 'buyers', ['buyer_id'], ['buyer_id'], ondelete='RESTRICT')

    # transactions.payment_id
    op.drop_constraint('transactions_payment_id_fkey', 'transactions', type_='foreignkey')
    op.create_foreign_key('transactions_payment_id_fkey', 'transactions', 'payments', ['payment_id'], ['payment_id'], ondelete='RESTRICT')


def downgrade() -> None:
    """Downgrade schema: restore previous foreign key ondelete behaviors."""
    op.drop_constraint('transactions_payment_id_fkey', 'transactions', type_='foreignkey')
    op.create_foreign_key('transactions_payment_id_fkey', 'transactions', 'payments', ['payment_id'], ['payment_id'], ondelete='SET NULL')

    op.drop_constraint('risk_scores_buyer_id_fkey', 'risk_scores', type_='foreignkey')
    op.create_foreign_key('risk_scores_buyer_id_fkey', 'risk_scores', 'buyers', ['buyer_id'], ['buyer_id'], ondelete='CASCADE')

    op.drop_constraint('payments_invoice_id_fkey', 'payments', type_='foreignkey')
    op.create_foreign_key('payments_invoice_id_fkey', 'payments', 'invoices', ['invoice_id'], ['invoice_id'], ondelete='CASCADE')

    op.drop_constraint('model_predictions_invoice_id_fkey', 'model_predictions', type_='foreignkey')
    op.create_foreign_key('model_predictions_invoice_id_fkey', 'model_predictions', 'invoices', ['invoice_id'], ['invoice_id'], ondelete='CASCADE')

    op.drop_constraint('invoices_supplier_id_fkey', 'invoices', type_='foreignkey')
    op.drop_constraint('invoices_buyer_id_fkey', 'invoices', type_='foreignkey')
    op.create_foreign_key('invoices_supplier_id_fkey', 'invoices', 'suppliers', ['supplier_id'], ['supplier_id'], ondelete='CASCADE')
    op.create_foreign_key('invoices_buyer_id_fkey', 'invoices', 'buyers', ['buyer_id'], ['buyer_id'], ondelete='CASCADE')

    op.drop_constraint('discount_offers_approved_by_fkey', 'discount_offers', type_='foreignkey')
    op.drop_constraint('discount_offers_invoice_id_fkey', 'discount_offers', type_='foreignkey')
    op.drop_constraint('discount_offers_buyer_id_fkey', 'discount_offers', type_='foreignkey')
    op.create_foreign_key('discount_offers_approved_by_fkey', 'discount_offers', 'users', ['approved_by'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('discount_offers_invoice_id_fkey', 'discount_offers', 'invoices', ['invoice_id'], ['invoice_id'], ondelete='CASCADE')
    op.create_foreign_key('discount_offers_buyer_id_fkey', 'discount_offers', 'buyers', ['buyer_id'], ['buyer_id'], ondelete='CASCADE')

    op.drop_constraint('buyers_primary_supplier_id_fkey', 'buyers', type_='foreignkey')
    op.create_foreign_key('buyers_primary_supplier_id_fkey', 'buyers', 'suppliers', ['primary_supplier_id'], ['supplier_id'], ondelete='SET NULL')

    op.drop_constraint('audit_logs_user_id_fkey', 'audit_logs', type_='foreignkey')
    op.create_foreign_key('audit_logs_user_id_fkey', 'audit_logs', 'users', ['user_id'], ['id'], ondelete='SET NULL')
