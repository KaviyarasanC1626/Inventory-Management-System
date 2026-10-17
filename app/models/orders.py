from decimal import Decimal

from app import db
from app.models.core import TimestampMixin


class PurchaseOrder(TimestampMixin, db.Model):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        db.CheckConstraint("total_amount >= 0", name="ck_purchase_total_nonnegative"),
        db.CheckConstraint("status IN ('pending', 'approved', 'received', 'cancelled')", name="ck_purchase_status"),
    )
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    notes = db.Column(db.String(1000))
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    received_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    received_at = db.Column(db.DateTime(timezone=True))
    supplier = db.relationship("Supplier")
    warehouse = db.relationship("Warehouse")
    items = db.relationship("PurchaseOrderItem", back_populates="order", cascade="all, delete-orphan", order_by="PurchaseOrderItem.id")


class PurchaseOrderItem(db.Model):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_purchase_item_quantity_positive"),
        db.CheckConstraint("unit_cost >= 0", name="ck_purchase_item_cost_nonnegative"),
    )
    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False)
    order = db.relationship("PurchaseOrder", back_populates="items")
    product = db.relationship("Product")


class SalesOrder(TimestampMixin, db.Model):
    __tablename__ = "sales_orders"
    __table_args__ = (
        db.UniqueConstraint("request_key", "created_by_id", name="uq_sales_idempotency_user"),
        db.CheckConstraint("status IN ('pending', 'completed', 'cancelled')", name="ck_sales_status"),
        db.CheckConstraint("subtotal >= 0 AND discount_amount >= 0 AND line_discount_total >= 0 AND discount_amount + line_discount_total <= subtotal AND tax_rate >= 0 AND tax_rate <= 100 AND tax_amount >= 0 AND total_amount >= 0", name="ck_sales_amounts_nonnegative"),
    )
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    request_key = db.Column(db.String(100), nullable=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    line_discount_total = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    customer_name = db.Column(db.String(180))
    notes = db.Column(db.String(1000))
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    completed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    completed_at = db.Column(db.DateTime(timezone=True))
    warehouse = db.relationship("Warehouse")
    items = db.relationship("SalesOrderItem", back_populates="order", cascade="all, delete-orphan", order_by="SalesOrderItem.id")


class SalesOrderItem(db.Model):
    __tablename__ = "sales_order_items"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_sales_item_quantity_positive"),
        db.CheckConstraint("unit_price >= 0 AND discount_amount >= 0", name="ck_sales_item_amounts_nonnegative"),
        db.CheckConstraint("discount_amount <= unit_price * quantity", name="ck_sales_item_discount_limit"),
    )
    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    order = db.relationship("SalesOrder", back_populates="items")
    product = db.relationship("Product")