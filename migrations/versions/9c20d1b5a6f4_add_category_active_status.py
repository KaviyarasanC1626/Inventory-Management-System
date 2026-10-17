"""Add active state to categories.

Revision ID: 9c20d1b5a6f4
Revises: 5a42c8e17b6d
Create Date: 2026-10-17 08:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "9c20d1b5a6f4"
down_revision = "5a42c8e17b6d"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=True))
    op.execute(sa.text("UPDATE categories SET is_active = 1 WHERE is_active IS NULL"))
    with op.batch_alter_table("categories") as batch_op:
        batch_op.alter_column("is_active", existing_type=sa.Boolean(), nullable=False)


def downgrade():
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_column("is_active")
