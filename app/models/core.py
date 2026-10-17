from datetime import datetime, timezone
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)
    users = db.relationship("User", back_populates="role")


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    role = db.relationship("Role", back_populates="users")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(TimestampMixin, db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    products = db.relationship("Product", back_populates="category")


class Supplier(TimestampMixin, db.Model):
    __tablename__ = "suppliers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(40))
    address = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Warehouse(TimestampMixin, db.Model):
    __tablename__ = "warehouses"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(30), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    inventory_rows = db.relationship("Inventory", back_populates="warehouse")


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"
    __table_args__ = (
        db.CheckConstraint("selling_price >= 0", name="ck_product_selling_price_nonnegative"),
        db.CheckConstraint("cost_price >= 0", name="ck_product_cost_price_nonnegative"),
        db.CheckConstraint("reorder_level >= 0", name="ck_product_reorder_nonnegative"),
    )
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    brand = db.Column(db.String(100))
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    selling_price = db.Column(db.Numeric(12, 2), nullable=False)
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    reorder_level = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    category = db.relationship("Category", back_populates="products")
    supplier = db.relationship("Supplier")
    inventory_rows = db.relationship("Inventory", back_populates="product")


class Inventory(TimestampMixin, db.Model):
    __tablename__ = "inventory"
    __table_args__ = (
        db.UniqueConstraint("product_id", "warehouse_id", name="uq_inventory_product_warehouse"),
        db.CheckConstraint("quantity >= 0", name="ck_inventory_nonnegative"),
        db.Index("ix_inventory_warehouse_product", "warehouse_id", "product_id"),
    )
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    product = db.relationship("Product", back_populates="inventory_rows")
    warehouse = db.relationship("Warehouse", back_populates="inventory_rows")


class StockMovement(db.Model):
    __tablename__ = "stock_movements"
    __table_args__ = (
        db.CheckConstraint("quantity_delta != 0", name="ck_stock_movement_nonzero"),
        db.CheckConstraint("movement_type IN ('receipt', 'issue', 'adjustment', 'transfer_in', 'transfer_out')", name="ck_stock_movement_type"),
        db.Index("ix_stock_movements_created_at", "created_at"),
    )
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity_delta = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(100))
    note = db.Column(db.String(500))
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    product = db.relationship("Product")
    warehouse = db.relationship("Warehouse")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.Integer)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)


def record_audit(action, entity, user=None, details=None, ip_address=None):
    db.session.add(AuditLog(
        user_id=getattr(user, "id", None), action=action, entity_type=entity.__class__.__name__,
        entity_id=getattr(entity, "id", None), details=details or {}, ip_address=ip_address,
    ))