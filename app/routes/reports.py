import csv
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO

from flask import Blueprint, Response, render_template, request
from sqlalchemy import func

from app import db
from app.models import PurchaseOrder, SalesOrder, StockMovement, Inventory, Product, Warehouse
from app.routes.products import roles_required

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _date_range():
    try:
        end_day = date.fromisoformat(request.args.get("to", date.today().isoformat()))
        start_day = date.fromisoformat(request.args.get("from", (end_day - timedelta(days=29)).isoformat()))
    except ValueError:
        return None, None
    if start_day > end_day or (end_day - start_day).days > 366:
        return None, None
    return (datetime.combine(start_day, time.min, tzinfo=timezone.utc),
            datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=timezone.utc))


def _safe_cell(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _csv_response(filename, headers, rows):
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_safe_cell(value) for value in row])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@reports_bp.get("")
@roles_required("admin", "inventory_manager")
def index():
    return render_template("reports/index.html")


@reports_bp.get("/sales.csv")
@roles_required("admin", "inventory_manager")
def sales_csv():
    start, end = _date_range()
    if start is None:
        return {"error": "invalid_date_range", "message": "Choose a valid range of up to 366 days."}, 400
    orders = SalesOrder.query.filter(
        SalesOrder.status == "completed", SalesOrder.completed_at >= start, SalesOrder.completed_at < end,
    ).order_by(SalesOrder.completed_at).all()
    return _csv_response(
        "sales-report.csv",
        ["Invoice", "Completed", "Customer", "Status", "Subtotal", "Item discounts", "Order discount", "Tax", "Total"],
        [[o.invoice_number, o.completed_at.isoformat() if o.completed_at else "", o.customer_name,
          o.status, o.subtotal, o.line_discount_total, o.discount_amount, o.tax_amount, o.total_amount]
         for o in orders],
    )


@reports_bp.get("/purchases.csv")
@roles_required("admin", "inventory_manager")
def purchases_csv():
    start, end = _date_range()
    if start is None:
        return {"error": "invalid_date_range", "message": "Choose a valid range of up to 366 days."}, 400
    orders = PurchaseOrder.query.filter(
        PurchaseOrder.created_at >= start, PurchaseOrder.created_at < end,
    ).order_by(PurchaseOrder.created_at).all()
    return _csv_response("purchase-report.csv", ["Order", "Created", "Supplier", "Warehouse", "Status", "Total"],
                         [[o.order_number, o.created_at.isoformat(), o.supplier.name, o.warehouse.name, o.status, o.total_amount] for o in orders])


@reports_bp.get("/inventory.csv")
@roles_required("admin", "inventory_manager")
def inventory_csv():
    start, end = _date_range()
    if start is None:
        return {"error": "invalid_date_range", "message": "Choose a valid range of up to 366 days."}, 400
    movements = StockMovement.query.filter(
        StockMovement.created_at >= start, StockMovement.created_at < end,
    ).order_by(StockMovement.created_at).all()
    return _csv_response("inventory-movements.csv", ["Date", "SKU", "Product", "Warehouse", "Movement", "Quantity change", "Reference", "Note"],
                         [[m.created_at.isoformat(), m.product.sku, m.product.name, m.warehouse.name,
                           m.movement_type, m.quantity_delta, m.reference, m.note] for m in movements])


@reports_bp.get("/low-stock.csv")
@roles_required("admin", "inventory_manager")
def low_stock_csv():
    try:
        as_of = date.fromisoformat(request.args.get("as_of", request.args.get("to", date.today().isoformat())))
    except ValueError:
        return {"error": "invalid_date", "message": "Choose a valid as-of date."}, 400
    if as_of > date.today():
        return {"error": "invalid_date", "message": "The as-of date cannot be in the future."}, 400
    cutoff = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=timezone.utc)
    later_changes = db.session.query(
        StockMovement.product_id, StockMovement.warehouse_id,
        func.sum(StockMovement.quantity_delta),
    ).filter(StockMovement.created_at >= cutoff).group_by(
        StockMovement.product_id, StockMovement.warehouse_id,
    ).all()
    movement_delta = {(product_id, warehouse_id): int(total or 0)
                      for product_id, warehouse_id, total in later_changes}
    historical_rows = []
    for row in Inventory.query.join(Product).join(Warehouse).filter(
        Product.is_active.is_(True), Warehouse.is_active.is_(True),
    ).order_by(Product.name, Warehouse.name).all():
        if row.created_at.date() > as_of:
            continue
        quantity = row.quantity - movement_delta.get((row.product_id, row.warehouse_id), 0)
        if quantity <= row.product.reorder_level:
            historical_rows.append([row.product.sku, row.product.name, row.warehouse.name,
                                    quantity, row.product.reorder_level])
    return _csv_response("low-stock-report.csv", ["As of", "SKU", "Product", "Warehouse", "Available", "Reorder level"],
                         [[as_of.isoformat(), *row] for row in historical_rows])