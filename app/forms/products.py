from decimal import Decimal, InvalidOperation
from uuid import uuid4

from app import db
from app.models import Category, Product, Supplier


def parse_product(form, default_sku=None, allowed_category_id=None, allowed_supplier_id=None):
    errors = {}
    sku = form.get("sku", "").strip().upper()
    if not sku:
        sku = default_sku
    if not sku:
        sku = f"SKU-{uuid4().hex[:10].upper()}"
        while Product.query.filter_by(sku=sku).first():
            sku = f"SKU-{uuid4().hex[:10].upper()}"
    name = form.get("name", "").strip()
    if not sku or len(sku) > 50:
        errors["sku"] = "SKU is required and must be 50 characters or fewer."
    if not name or len(name) > 180:
        errors["name"] = "Name is required and must be 180 characters or fewer."
    try:
        selling_price = Decimal(form.get("selling_price", ""))
        cost_price = Decimal(form.get("cost_price", "0") or "0")
        if not selling_price.is_finite() or selling_price < 0 or not cost_price.is_finite() or cost_price < 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        errors["price"] = "Enter valid non-negative prices."
        selling_price, cost_price = Decimal("0"), Decimal("0")
    try:
        reorder_level = int(form.get("reorder_level", "0") or 0)
        if reorder_level < 0:
            raise ValueError
    except (ValueError, TypeError):
        errors["reorder_level"] = "Reorder level must be a non-negative whole number."
        reorder_level = 0
    category_id = form.get("category_id") or None
    try:
        category_id = int(category_id) if category_id else None
        if category_id:
            category = db.session.get(Category, category_id)
            if category is None or (not category.is_active and category_id != allowed_category_id):
                raise ValueError
    except (ValueError, TypeError):
        errors["category_id"] = "Select a valid category."
        category_id = None
    supplier_id = form.get("supplier_id") or None
    try:
        supplier_id = int(supplier_id) if supplier_id else None
        if supplier_id:
            supplier = db.session.get(Supplier, supplier_id)
            if supplier is None or (not supplier.is_active and supplier_id != allowed_supplier_id):
                raise ValueError
    except (ValueError, TypeError):
        errors["supplier_id"] = "Select a valid supplier."
        supplier_id = None
    return {
        "sku": sku, "name": name, "brand": form.get("brand", "").strip() or None,
        "description": form.get("description", "").strip() or None,
        "selling_price": selling_price, "cost_price": cost_price,
        "reorder_level": reorder_level, "category_id": category_id, "supplier_id": supplier_id,
    }, errors