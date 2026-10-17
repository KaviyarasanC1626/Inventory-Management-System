from functools import wraps

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app import db
from app.forms import parse_product
from app.models import (
    Category, Inventory, Product, PurchaseOrderItem, SalesOrderItem, StockMovement, Supplier, record_audit,
)

products_bp = Blueprint("products", __name__, url_prefix="/products")
EDIT_ROLES = {"admin", "inventory_manager"}


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role.name not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def _product_payload(product):
    payload = {
        "id": product.id, "sku": product.sku, "name": product.name, "brand": product.brand,
        "category": product.category.name if product.category else None,
        "supplier": product.supplier.name if product.supplier else None,
        "selling_price": str(product.selling_price),
        "reorder_level": product.reorder_level, "is_active": product.is_active,
    }
    if current_user.role.name in EDIT_ROLES:
        payload["cost_price"] = str(product.cost_price)
    return payload


@products_bp.get("")
@login_required
def list_products():
    requested_status = request.args.get("status", "active")
    if current_user.role.name not in EDIT_ROLES or requested_status not in {"active", "archived", "all"}:
        requested_status = "active"
    query = Product.query
    if requested_status == "active":
        query = query.filter_by(is_active=True)
    elif requested_status == "archived":
        query = query.filter_by(is_active=False)
    search = request.args.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern), Product.brand.ilike(pattern)))
    category_id = request.args.get("category", type=int)
    if category_id:
        query = query.filter_by(category_id=category_id)
    sort_columns = {"name": Product.name, "sku": Product.sku, "price": Product.selling_price}
    sort_column = sort_columns.get(request.args.get("sort", "name"), Product.name)
    ordering = sort_column.desc() if request.args.get("direction") == "desc" else sort_column.asc()
    pagination = query.order_by(ordering, Product.id.asc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, error_out=False,
    )
    if request.accept_mimetypes.best == "application/json":
        return jsonify(items=[_product_payload(item) for item in pagination.items], page=pagination.page,
                       pages=pagination.pages, total=pagination.total)
    return render_template(
        "products/list.html", pagination=pagination,
        categories=Category.query.order_by(Category.name).all(), search=search,
        status_filter=requested_status,
    )


@products_bp.route("/new", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def create_product():
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    if request.method == "POST":
        values, errors = parse_product(request.form)
        if Product.query.filter_by(sku=values["sku"]).first():
            errors["sku"] = "That SKU is already in use."
        if errors:
            for message in errors.values():
                flash(message, "danger")
        else:
            product = Product(**values, created_by_id=current_user.id, updated_by_id=current_user.id)
            db.session.add(product)
            db.session.flush()
            record_audit("product.created", product, current_user, {"sku": product.sku}, request.remote_addr)
            db.session.commit()
            flash("Product created.", "success")
            return redirect(url_for("products.list_products"))
    return render_template("products/form.html", product=None, categories=categories,
                           suppliers=Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all())


@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@roles_required(*EDIT_ROLES)
def edit_product(product_id):
    product = db.get_or_404(Product, product_id)
    categories_query = Category.query.filter_by(is_active=True)
    if product.category_id:
        categories_query = Category.query.filter(
            (Category.is_active.is_(True)) | (Category.id == product.category_id),
        )
    categories = categories_query.order_by(Category.name).all()
    if request.method == "POST":
        values, errors = parse_product(
            request.form, default_sku=product.sku,
            allowed_category_id=product.category_id, allowed_supplier_id=product.supplier_id,
        )
        duplicate = Product.query.filter(Product.sku == values["sku"], Product.id != product.id).first()
        if duplicate:
            errors["sku"] = "That SKU is already in use."
        if errors:
            for message in errors.values():
                flash(message, "danger")
        else:
            before = {"sku": product.sku, "name": product.name}
            for key, value in values.items():
                setattr(product, key, value)
            product.updated_by_id = current_user.id
            record_audit("product.updated", product, current_user, {"before": before}, request.remote_addr)
            db.session.commit()
            flash("Product updated.", "success")
            return redirect(url_for("products.list_products"))
    suppliers_query = Supplier.query.filter_by(is_active=True)
    if product.supplier_id:
        suppliers_query = Supplier.query.filter(
            (Supplier.is_active.is_(True)) | (Supplier.id == product.supplier_id),
        )
    return render_template("products/form.html", product=product, categories=categories,
                           suppliers=suppliers_query.order_by(Supplier.name).all())


@products_bp.post("/<int:product_id>/archive")
@roles_required(*EDIT_ROLES)
def archive_product(product_id):
    product = db.get_or_404(Product, product_id)
    product.is_active = False
    product.updated_by_id = current_user.id
    record_audit("product.archived", product, current_user, {"sku": product.sku}, request.remote_addr)
    db.session.commit()
    flash("Product archived.", "success")
    return redirect(url_for("products.list_products"))


@products_bp.post("/<int:product_id>/toggle-active")
@roles_required(*EDIT_ROLES)
def toggle_product(product_id):
    product = db.get_or_404(Product, product_id)
    product.is_active = not product.is_active
    product.updated_by_id = current_user.id
    action = "product.reactivated" if product.is_active else "product.archived"
    record_audit(action, product, current_user, {"sku": product.sku}, request.remote_addr)
    db.session.commit()
    flash(f"Product {'reactivated' if product.is_active else 'archived'}.", "success")
    return redirect(url_for("products.list_products", status="all" if not product.is_active else None))


@products_bp.post("/<int:product_id>/delete")
@roles_required(*EDIT_ROLES)
def delete_product(product_id):
    product = db.get_or_404(Product, product_id)
    has_history = any((
        Inventory.query.filter_by(product_id=product.id).first(),
        StockMovement.query.filter_by(product_id=product.id).first(),
        PurchaseOrderItem.query.filter_by(product_id=product.id).first(),
        SalesOrderItem.query.filter_by(product_id=product.id).first(),
    ))
    if has_history:
        flash("This product has inventory or order history. Archive it instead of deleting it.", "warning")
    else:
        record_audit("product.deleted", product, current_user, {"sku": product.sku, "name": product.name}, request.remote_addr)
        db.session.delete(product)
        db.session.commit()
        flash("Unused product deleted.", "success")
    return redirect(url_for("products.list_products", status="all"))


@products_bp.get("/api")
@login_required
def product_api_list():
    query = Product.query.filter_by(is_active=True)
    search = request.args.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern)))
    page = query.order_by(Product.name).paginate(page=request.args.get("page", 1, type=int), per_page=20, error_out=False)
    return jsonify(data=[_product_payload(item) for item in page.items], meta={"page": page.page, "pages": page.pages, "total": page.total})