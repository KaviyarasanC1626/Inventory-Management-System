from app import db
from app.models import Inventory, Product, StockMovement, Warehouse


class StockError(ValueError):
    pass


def _locked_rows(product_ids, warehouse_id, allow_create=False):
    warehouse = db.session.get(Warehouse, warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise StockError("Warehouse does not exist or is inactive.")
    product_ids = sorted(set(product_ids))
    products = Product.query.filter(Product.id.in_(product_ids)).order_by(Product.id).with_for_update().all()
    if len(products) != len(product_ids):
        raise StockError("One or more products do not exist.")
    rows = {}
    for product in products:
        row = Inventory.query.filter_by(product_id=product.id, warehouse_id=warehouse_id).with_for_update().first()
        if row is None and allow_create:
            row = Inventory(product_id=product.id, warehouse_id=warehouse_id, quantity=0)
            db.session.add(row)
            db.session.flush()
        if row is None:
            raise StockError(f"No stock record exists for product {product.sku} in this warehouse.")
        rows[product.id] = row
    return rows


def _movement(product_id, warehouse_id, movement_type, delta, user_id, reference=None, note=None):
    db.session.add(StockMovement(
        product_id=product_id, warehouse_id=warehouse_id, movement_type=movement_type,
        quantity_delta=delta, created_by_id=user_id, reference=reference, note=note,
    ))


def adjust_stock(product_id, warehouse_id, delta, user_id, note=None):
    if not isinstance(delta, int) or delta == 0:
        raise StockError("Adjustment must be a non-zero whole number.")
    row = _locked_rows([product_id], warehouse_id, allow_create=delta > 0)[product_id]
    if row.quantity + delta < 0:
        raise StockError("Adjustment would make available stock negative.")
    row.quantity += delta
    _movement(product_id, warehouse_id, "adjustment", delta, user_id, note=note)
    return row


def receive_stock(items, warehouse_id, user_id, reference):
    quantities = {}
    for item in items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    rows = _locked_rows(quantities, warehouse_id, allow_create=True)
    for product_id, quantity in quantities.items():
        rows[product_id].quantity += quantity
        _movement(product_id, warehouse_id, "receipt", quantity, user_id, reference=reference)


def issue_stock(items, warehouse_id, user_id, reference):
    quantities = {}
    for item in items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    rows = _locked_rows(quantities, warehouse_id)
    for product_id, quantity in quantities.items():
        if rows[product_id].quantity < quantity:
            raise StockError(f"Insufficient stock for {rows[product_id].product.sku}.")
    for product_id, quantity in quantities.items():
        rows[product_id].quantity -= quantity
        _movement(product_id, warehouse_id, "issue", -quantity, user_id, reference=reference)


def transfer_stock(product_id, source_id, destination_id, quantity, user_id, note=None):
    if source_id == destination_id:
        raise StockError("Source and destination warehouses must differ.")
    if not isinstance(quantity, int) or quantity <= 0:
        raise StockError("Transfer quantity must be a positive whole number.")
    if any(db.session.get(Warehouse, warehouse_id) is None or not db.session.get(Warehouse, warehouse_id).is_active
           for warehouse_id in (source_id, destination_id)):
        raise StockError("Source or destination warehouse does not exist or is inactive.")
    product = Product.query.filter_by(id=product_id).with_for_update().first()
    if product is None:
        raise StockError("Product does not exist.")
    source = Inventory.query.filter_by(product_id=product_id, warehouse_id=source_id).with_for_update().first()
    if source is None or source.quantity < quantity:
        raise StockError("Insufficient source stock for this transfer.")
    destination = Inventory.query.filter_by(product_id=product_id, warehouse_id=destination_id).with_for_update().first()
    if destination is None:
        destination = Inventory(product_id=product_id, warehouse_id=destination_id, quantity=0)
        db.session.add(destination)
        db.session.flush()
    source.quantity -= quantity
    destination.quantity += quantity
    _movement(product_id, source_id, "transfer_out", -quantity, user_id, reference=f"to:{destination_id}", note=note)
    _movement(product_id, destination_id, "transfer_in", quantity, user_id, reference=f"from:{source_id}", note=note)