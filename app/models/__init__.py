from app import db, login_manager
from app.models.core import AuditLog, Category, Inventory, Product, Role, StockMovement, Supplier, User, Warehouse, record_audit
from app.models.orders import PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


__all__ = ["AuditLog", "Category", "Inventory", "Product", "PurchaseOrder", "PurchaseOrderItem", "Role", "SalesOrder", "SalesOrderItem", "StockMovement", "Supplier", "User", "Warehouse", "record_audit"]