"""Add content hash column to documents.

Revision ID: a7c91e2f4b60
Revises: 9c38274596fb
"""

from alembic import op
import sqlalchemy as sa

revision = "a7c91e2f4b60"
down_revision = "9c38274596fb"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_documents_company_type_version_hash",
        "documents",
        ["company_id", "document_type", "version", "content_hash"],
    )


def downgrade():
    op.drop_constraint(
        "uq_documents_company_type_version_hash",
        "documents",
        type_="unique",
    )
    op.drop_column("documents", "content_hash")