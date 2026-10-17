import json

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Product, PurchaseOrder, Supplier, Warehouse, record_audit
from app.routes.products import roles_required
from app.services.orders import OrderError, approve_purchase_order, cancel_purchase_order, create_purchase_order, receive_purchase_order

purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")
MANAGER_ROLES = ("admin", "inventory_manager")


def _data(order):
    return {"id": order.id, "order_number": order.order_number, "supplier": order.supplier.name,
            "warehouse": order.warehouse.name, "status": order.status, "total_amount": str(order.total_amount),
            "items": [{"sku": item.product.sku, "product": item.product.name, "quantity": item.quantity,
                       "unit_cost": str(item.unit_cost)} for item in order.items]}


@purchases_bp.get("")
@roles_required(*MANAGER_ROLES)
def index():
    orders = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).limit(100).all()
    return render_template("purchases/index.html", orders=orders)


@purchases_bp.get("/new")
@roles_required(*MANAGER_ROLES)
def new():
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).all()
    return render_template("purchases/new.html", products=products, suppliers=suppliers, warehouses=warehouses)


@purchases_bp.route("/api", methods=["GET", "POST"])
@roles_required(*MANAGER_ROLES)
def api_orders():
    if request.method == "GET":
        return jsonify(data=[_data(order) for order in PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).limit(100).all()])
    payload = request.get_json(silent=True) or request.form
    try:
        items = payload.get("items", [])
        if isinstance(items, str):
            items = json.loads(items)
        order = create_purchase_order(int(payload.get("supplier_id", 0)), int(payload.get("warehouse_id", 0)),
                                      items, current_user.id, payload.get("notes"))
        record_audit("purchase.created", order, current_user, {"order_number": order.order_number}, request.remote_addr)
        db.session.commit()
    except (OrderError, ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="invalid_purchase_order", message=str(error)), 400
    return jsonify(data=_data(order)), 201


@purchases_bp.post("/<int:order_id>/approve")
@roles_required(*MANAGER_ROLES)
def approve(order_id):
    try:
        order = approve_purchase_order(order_id, current_user.id)
        record_audit("purchase.approved", order, current_user, {}, request.remote_addr)
        db.session.commit()
    except OrderError as error:
        db.session.rollback()
        return jsonify(error="invalid_order_transition", message=str(error)), 409
    if request.is_json:
        return jsonify(data=_data(order))
    flash("Purchase order approved.", "success")
    return redirect(url_for("purchases.index"))


@purchases_bp.post("/<int:order_id>/receive")
@roles_required(*MANAGER_ROLES)
def receive(order_id):
    try:
        order = receive_purchase_order(order_id, current_user.id)
        record_audit("purchase.received", order, current_user, {}, request.remote_addr)
        db.session.commit()
    except OrderError as error:
        db.session.rollback()
        return jsonify(error="invalid_order_transition", message=str(error)), 409
    if request.is_json:
        return jsonify(data=_data(order))
    flash("Purchase received and inventory updated.", "success")
    return redirect(url_for("purchases.index"))


@purchases_bp.post("/<int:order_id>/cancel")
@roles_required(*MANAGER_ROLES)
def cancel(order_id):
    try:
        order = cancel_purchase_order(order_id)
        record_audit("purchase.cancelled", order, current_user, {}, request.remote_addr)
        db.session.commit()
    except OrderError as error:
        db.session.rollback()
        return jsonify(error="invalid_order_transition", message=str(error)), 409
    if request.is_json:
        return jsonify(data=_data(order))
    flash("Purchase order cancelled.", "success")
    return redirect(url_for("purchases.index"))