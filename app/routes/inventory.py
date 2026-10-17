from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Inventory, Product, StockMovement, Warehouse, record_audit
from app.routes.products import roles_required
from app.services.stock import StockError, adjust_stock, transfer_stock

inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")
MANAGER_ROLES = ("admin", "inventory_manager")


@inventory_bp.get("")
@login_required
def index():
    rows = Inventory.query.join(Product).join(Warehouse).filter(Product.is_active.is_(True)).order_by(Product.name, Warehouse.name).all()
    warehouses = Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).all()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    return render_template("inventory/index.html", rows=rows, warehouses=warehouses, products=products)


@inventory_bp.get("/api")
@login_required
def api_list():
    rows = Inventory.query.join(Product).join(Warehouse).filter(Product.is_active.is_(True)).order_by(Product.name).all()
    return jsonify(data=[{"product_id": row.product_id, "sku": row.product.sku, "product": row.product.name,
                          "warehouse_id": row.warehouse_id, "warehouse": row.warehouse.name,
                          "quantity": row.quantity, "reorder_level": row.product.reorder_level,
                          "low_stock": row.quantity <= row.product.reorder_level} for row in rows])


@inventory_bp.get("/movements")
@roles_required(*MANAGER_ROLES)
def movements():
    page = StockMovement.query.order_by(StockMovement.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=50, error_out=False,
    )
    return render_template("inventory/movements.html", pagination=page)


@inventory_bp.post("/adjustments")
@roles_required(*MANAGER_ROLES)
def adjustment():
    payload = request.get_json(silent=True) or request.form
    try:
        row = adjust_stock(
            int(payload.get("product_id", 0)), int(payload.get("warehouse_id", 0)),
            int(payload.get("delta", 0)), current_user.id, payload.get("note"),
        )
        record_audit("inventory.adjusted", row, current_user, {"delta": int(payload["delta"])}, request.remote_addr)
        db.session.commit()
    except (ValueError, TypeError, StockError) as error:
        db.session.rollback()
        if request.is_json:
            return jsonify(error="invalid_stock_operation", message=str(error)), 400
        flash(str(error), "danger")
        return redirect(url_for("inventory.index"))
    if request.is_json:
        return jsonify(data={"product_id": row.product_id, "warehouse_id": row.warehouse_id, "quantity": row.quantity}), 200
    flash("Stock adjusted.", "success")
    return redirect(url_for("inventory.index"))


@inventory_bp.post("/transfers")
@roles_required(*MANAGER_ROLES)
def transfer():
    payload = request.get_json(silent=True) or request.form
    try:
        product_id = int(payload.get("product_id", 0))
        source_id = int(payload.get("source_id", 0))
        destination_id = int(payload.get("destination_id", 0))
        quantity = int(payload.get("quantity", 0))
        transfer_stock(product_id, source_id, destination_id, quantity, current_user.id, payload.get("note"))
        record_audit("inventory.transferred", db.session.get(Product, product_id), current_user,
                 {"source_id": source_id, "destination_id": destination_id, "quantity": quantity}, request.remote_addr)
        db.session.commit()
    except (ValueError, TypeError, StockError) as error:
        db.session.rollback()
        if not request.is_json:
            flash(str(error), "danger")
            return redirect(url_for("inventory.index"))
        return jsonify(error="invalid_stock_operation", message=str(error)), 400
    if not request.is_json:
        flash("Stock transferred.", "success")
        return redirect(url_for("inventory.index"))
    return jsonify(data={"message": "Stock transferred."}), 200


@inventory_bp.get("/warehouses")
@login_required
def warehouses():
    return jsonify(data=[{"id": row.id, "name": row.name, "code": row.code}
                         for row in Warehouse.query.filter_by(is_active=True).order_by(Warehouse.name).all()])