from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Product, SalesOrder, Warehouse, record_audit
from app.routes.products import roles_required
from app.services.orders import OrderError, cancel_sales_order, complete_sales_order, create_sales_order
from app.services.stock import StockError

sales_bp = Blueprint("sales", __name__, url_prefix="/sales")
SALES_ROLES = ("admin", "sales_staff")


def _require_order_access(order):
    if current_user.role.name == "sales_staff" and order.created_by_id != current_user.id:
        abort(403)


def _data(order):
    return {"id": order.id, "invoice_number": order.invoice_number, "status": order.status,
            "customer_name": order.customer_name, "warehouse": order.warehouse.name,
            "subtotal": str(order.subtotal), "discount_amount": str(order.discount_amount),
            "line_discount_total": str(order.line_discount_total),
            "tax_amount": str(order.tax_amount), "total_amount": str(order.total_amount),
            "items": [{"sku": item.product.sku, "product": item.product.name, "quantity": item.quantity,
                       "unit_price": str(item.unit_price), "discount_amount": str(item.discount_amount)} for item in order.items]}


@sales_bp.get("")
@roles_required(*SALES_ROLES)
def index():
    query = SalesOrder.query
    if current_user.role.name == "sales_staff":
        query = query.filter_by(created_by_id=current_user.id)
    orders = query.order_by(SalesOrder.created_at.desc()).limit(100).all()
    return render_template("sales/index.html", orders=orders)


@sales_bp.get("/new")
@roles_required(*SALES_ROLES)
def new():
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).all()
    return render_template("sales/new.html", products=products, warehouses=warehouses)


@sales_bp.route("/api", methods=["GET", "POST"])
@roles_required(*SALES_ROLES)
def api_orders():
    if request.method == "GET":
        query = SalesOrder.query
        if current_user.role.name == "sales_staff":
            query = query.filter_by(created_by_id=current_user.id)
        return jsonify(data=[_data(order) for order in query.order_by(SalesOrder.created_at.desc()).limit(100).all()])
    payload = request.get_json(silent=True) or request.form
    idempotency_key = request.headers.get("Idempotency-Key") or payload.get("request_key")
    try:
        items = payload.get("items", [])
        if isinstance(items, str):
            import json
            items = json.loads(items)
        order, created = create_sales_order(
            int(payload.get("warehouse_id", 0)), items, current_user.id,
            payload.get("customer_name"), payload.get("discount_amount", 0), payload.get("tax_rate", 0),
            payload.get("notes"), idempotency_key,
        )
        if created:
            record_audit("sale.created", order, current_user, {"invoice_number": order.invoice_number}, request.remote_addr)
        db.session.commit()
    except (OrderError, ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="invalid_sales_order", message=str(error)), 400
    except IntegrityError:
        db.session.rollback()
        existing = SalesOrder.query.filter_by(request_key=idempotency_key, created_by_id=current_user.id).first() if idempotency_key else None
        if existing:
            return jsonify(data=_data(existing)), 200
        return jsonify(error="sales_order_conflict", message="The order conflicts with an existing record."), 409
    return jsonify(data=_data(order)), 201 if created else 200


@sales_bp.post("/<int:order_id>/complete")
@roles_required(*SALES_ROLES)
def complete(order_id):
    try:
        existing = db.get_or_404(SalesOrder, order_id)
        _require_order_access(existing)
        order = complete_sales_order(order_id, current_user.id)
        record_audit("sale.completed", order, current_user, {}, request.remote_addr)
        db.session.commit()
    except (OrderError, StockError) as error:
        db.session.rollback()
        return jsonify(error="sales_completion_failed", message=str(error)), 409
    if request.is_json:
        return jsonify(data=_data(order))
    flash("Sale completed and stock deducted.", "success")
    return redirect(url_for("sales.index"))


@sales_bp.post("/<int:order_id>/cancel")
@roles_required(*SALES_ROLES)
def cancel(order_id):
    try:
        existing = db.get_or_404(SalesOrder, order_id)
        _require_order_access(existing)
        order = cancel_sales_order(order_id)
        record_audit("sale.cancelled", order, current_user, {}, request.remote_addr)
        db.session.commit()
    except OrderError as error:
        db.session.rollback()
        return jsonify(error="invalid_order_transition", message=str(error)), 409
    if request.is_json:
        return jsonify(data=_data(order))
    flash("Sales order cancelled.", "success")
    return redirect(url_for("sales.index"))


@sales_bp.get("/<int:order_id>/invoice")
@roles_required(*SALES_ROLES)
def invoice(order_id):
    order = db.get_or_404(SalesOrder, order_id)
    _require_order_access(order)
    return render_template("sales/invoice.html", order=order)