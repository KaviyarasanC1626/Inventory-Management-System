"""Add catalog price and sales total constraints.

Revision ID: 5a42c8e17b6d
Revises: 0742f9f617ab
Create Date: 2026-10-17 07:42:00.000000
"""
from alembic import op


revision = "5a42c8e17b6d"
down_revision = "0742f9f617ab"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products") as batch_op:
        batch_op.create_check_constraint("ck_product_selling_price_nonnegative", "selling_price >= 0")
        batch_op.create_check_constraint("ck_product_cost_price_nonnegative", "cost_price >= 0")
        batch_op.create_check_constraint("ck_product_reorder_nonnegative", "reorder_level >= 0")
    with op.batch_alter_table("sales_orders") as batch_op:
        batch_op.drop_constraint("ck_sales_amounts_nonnegative", type_="check")
        batch_op.create_check_constraint(
            "ck_sales_amounts_nonnegative",
            "subtotal >= 0 AND discount_amount >= 0 AND line_discount_total >= 0 "
            "AND discount_amount + line_discount_total <= subtotal "
            "AND tax_rate >= 0 AND tax_rate <= 100 AND tax_amount >= 0 AND total_amount >= 0",
        )


def downgrade():
    with op.batch_alter_table("sales_orders") as batch_op:
        batch_op.drop_constraint("ck_sales_amounts_nonnegative", type_="check")
        batch_op.create_check_constraint(
            "ck_sales_amounts_nonnegative",
            "subtotal >= 0 AND discount_amount >= 0 AND line_discount_total >= 0 "
            "AND tax_amount >= 0 AND total_amount >= 0",
        )
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_constraint("ck_product_reorder_nonnegative", type_="check")
        batch_op.drop_constraint("ck_product_cost_price_nonnegative", type_="check")
        batch_op.drop_constraint("ck_product_selling_price_nonnegative", type_="check")