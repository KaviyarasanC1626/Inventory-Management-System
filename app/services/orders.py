from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from app import db
from app.models import Product, PurchaseOrder, PurchaseOrderItem, SalesOrder, SalesOrderItem, Supplier, Warehouse
from app.services.stock import issue_stock, receive_stock

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999.99")


class OrderError(ValueError):
    pass


def _decimal(value, label, minimum=Decimal("0"), maximum=None):
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise OrderError(f"{label} must be a valid amount.") from None
    allowed_maximum = min(maximum, MAX_AMOUNT) if maximum is not None else MAX_AMOUNT
    if not amount.is_finite() or amount < minimum or amount > allowed_maximum:
        raise OrderError(f"{label} is outside the allowed range.")
    return amount


def _quantity(value):
    try:
        quantity = int(value)
    except (ValueError, TypeError):
        raise OrderError("Quantity must be a positive whole number.") from None
    if quantity <= 0:
        raise OrderError("Quantity must be a positive whole number.")
    return quantity


def create_purchase_order(supplier_id, warehouse_id, item_data, user_id, notes=None):
    supplier = db.session.get(Supplier, supplier_id)
    warehouse = db.session.get(Warehouse, warehouse_id)
    if supplier is None or not supplier.is_active or warehouse is None or not warehouse.is_active:
        raise OrderError("Choose an active supplier and warehouse.")
    if not isinstance(item_data, list) or not item_data:
        raise OrderError("At least one purchase item is required.")
    order = PurchaseOrder(
        order_number=f"PO-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}",
        supplier_id=supplier_id, warehouse_id=warehouse_id, created_by_id=user_id,
        notes=(notes or "").strip() or None,
    )
    total = Decimal("0.00")
    for item in item_data:
        if not isinstance(item, dict):
            raise OrderError("Each purchase line must be an object.")
        product_id = int(item.get("product_id", 0))
        product = db.session.get(Product, product_id)
        if product is None or not product.is_active:
            raise OrderError("Every purchase item must reference an active product.")
        quantity = _quantity(item.get("quantity"))
        cost = _decimal(item.get("unit_cost", product.cost_price), "Unit cost")
        total += cost * quantity
        order.items.append(PurchaseOrderItem(product=product, quantity=quantity, unit_cost=cost))
    order.total_amount = total.quantize(CENT)
    db.session.add(order)
    db.session.flush()
    return order


def approve_purchase_order(order_id, user_id):
    order = PurchaseOrder.query.filter_by(id=order_id).with_for_update().first()
    if order is None:
        raise OrderError("Purchase order was not found.")
    if order.status != "pending":
        raise OrderError(f"Only pending orders can be approved (current status: {order.status}).")
    order.status = "approved"
    order.approved_by_id = user_id
    return order


def receive_purchase_order(order_id, user_id):
    order = PurchaseOrder.query.filter_by(id=order_id).with_for_update().first()
    if order is None:
        raise OrderError("Purchase order was not found.")
    if order.status != "approved":
        raise OrderError(f"Only approved orders can be received (current status: {order.status}).")
    receive_stock(order.items, order.warehouse_id, user_id, order.order_number)
    order.status = "received"
    order.received_by_id = user_id
    order.received_at = datetime.now(timezone.utc)
    return order


def cancel_purchase_order(order_id):
    order = PurchaseOrder.query.filter_by(id=order_id).with_for_update().first()
    if order is None:
        raise OrderError("Purchase order was not found.")
    if order.status not in {"pending", "approved"}:
        raise OrderError("Only pending or approved purchase orders can be cancelled.")
    order.status = "cancelled"
    return order


def create_sales_order(warehouse_id, item_data, user_id, customer_name=None, discount_amount=0, tax_rate=0, notes=None, request_key=None):
    if request_key:
        if not isinstance(request_key, str) or len(request_key) > 100:
            raise OrderError("Idempotency key must be 100 characters or fewer.")
        existing = SalesOrder.query.filter_by(request_key=request_key, created_by_id=user_id).first()
        if existing:
            return existing, False
    warehouse = db.session.get(Warehouse, warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise OrderError("Choose an active warehouse.")
    if not isinstance(item_data, list) or not item_data:
        raise OrderError("At least one sales item is required.")
    order = SalesOrder(
        invoice_number=f"INV-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}",
        request_key=request_key, warehouse_id=warehouse_id, created_by_id=user_id,
        customer_name=(customer_name or "").strip() or None,
        notes=(notes or "").strip() or None,
    )
    subtotal = Decimal("0.00")
    line_discount_total = Decimal("0.00")
    for item in item_data:
        if not isinstance(item, dict):
            raise OrderError("Each sales line must be an object.")
        try:
            product = db.session.get(Product, int(item.get("product_id", 0)))
        except (TypeError, ValueError):
            raise OrderError("Each sales line must reference a valid product.") from None
        if product is None or not product.is_active:
            raise OrderError("Every sales item must reference an active product.")
        quantity = _quantity(item.get("quantity"))
        unit_price = product.selling_price
        line_discount = _decimal(item.get("discount_amount", 0), "Line discount")
        line_subtotal = unit_price * quantity
        if line_discount > line_subtotal:
            raise OrderError("A line discount cannot exceed its line subtotal.")
        subtotal += line_subtotal
        line_discount_total += line_discount
        order.items.append(SalesOrderItem(
            product=product, quantity=quantity, unit_price=unit_price, discount_amount=line_discount,
        ))
    header_discount = _decimal(discount_amount, "Order discount")
    if header_discount + line_discount_total > subtotal:
        raise OrderError("Order discount cannot exceed the subtotal.")
    tax = _decimal(tax_rate, "Tax rate", maximum=Decimal("100"))
    taxable = subtotal - line_discount_total - header_discount
    tax_amount = (taxable * tax / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    order.subtotal = subtotal.quantize(CENT)
    order.discount_amount = header_discount
    order.line_discount_total = line_discount_total.quantize(CENT)
    order.tax_rate = tax
    order.tax_amount = tax_amount
    order.total_amount = (taxable + tax_amount).quantize(CENT)
    db.session.add(order)
    db.session.flush()
    return order, True


def complete_sales_order(order_id, user_id):
    order = SalesOrder.query.filter_by(id=order_id).with_for_update().first()
    if order is None:
        raise OrderError("Sales order was not found.")
    if order.status != "pending":
        raise OrderError(f"Only pending orders can be completed (current status: {order.status}).")
    issue_stock(order.items, order.warehouse_id, user_id, order.invoice_number)
    order.status = "completed"
    order.completed_by_id = user_id
    order.completed_at = datetime.now(timezone.utc)
    return order


def cancel_sales_order(order_id):
    order = SalesOrder.query.filter_by(id=order_id).with_for_update().first()
    if order is None:
        raise OrderError("Sales order was not found.")
    if order.status != "pending":
        raise OrderError("Only pending sales orders can be cancelled.")
    order.status = "cancelled"
    return order