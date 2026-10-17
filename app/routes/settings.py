from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.models import (
    AuditLog, Category, Product, PurchaseOrder, Role, SalesOrder, StockMovement,
    Supplier, User, Warehouse, record_audit,
)
from app.routes.products import roles_required

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/categories", methods=["GET", "POST"])
@roles_required("admin")
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        if not name or len(name) > 100:
            flash("Enter a category name of 1 to 100 characters.", "danger")
        elif Category.query.filter_by(name=name).first():
            flash("That category already exists.", "danger")
        else:
            category = Category(name=name, description=description)
            db.session.add(category)
            db.session.flush()
            record_audit("category.created", category, current_user, {}, request.remote_addr)
            db.session.commit()
            flash("Category added.", "success")
            return redirect(url_for("settings.categories"))
    return render_template("settings/categories.html", categories=Category.query.order_by(Category.name).all())


@settings_bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit_category(category_id):
    category = db.get_or_404(Category, category_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        duplicate = Category.query.filter(Category.name == name, Category.id != category.id).first()
        if not name or len(name) > 100:
            flash("Enter a category name of 1 to 100 characters.", "danger")
        elif duplicate:
            flash("That category name is already in use.", "danger")
        else:
            before = {"name": category.name, "description": category.description}
            category.name = name
            category.description = description
            record_audit("category.updated", category, current_user, {"before": before}, request.remote_addr)
            db.session.commit()
            flash("Category updated.", "success")
            return redirect(url_for("settings.categories"))
    return render_template("settings/category_form.html", category=category)


@settings_bp.post("/categories/<int:category_id>/toggle-active")
@roles_required("admin")
def toggle_category(category_id):
    category = db.get_or_404(Category, category_id)
    category.is_active = not category.is_active
    action = "category.activated" if category.is_active else "category.deactivated"
    record_audit(action, category, current_user, {}, request.remote_addr)
    db.session.commit()
    flash(f"Category {'activated' if category.is_active else 'deactivated'}.", "success")
    return redirect(url_for("settings.categories"))


@settings_bp.post("/categories/<int:category_id>/delete")
@roles_required("admin")
def delete_category(category_id):
    category = db.get_or_404(Category, category_id)
    if Product.query.filter_by(category_id=category.id).first():
        flash("This category is in use by products. Deactivate it to retain history.", "warning")
    else:
        record_audit("category.deleted", category, current_user, {"name": category.name}, request.remote_addr)
        db.session.delete(category)
        db.session.commit()
        flash("Unused category deleted.", "success")
    return redirect(url_for("settings.categories"))


@settings_bp.route("/suppliers", methods=["GET", "POST"])
@roles_required("admin", "inventory_manager")
def suppliers():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower() or None
        phone = request.form.get("phone", "").strip() or None
        address = request.form.get("address", "").strip() or None
        if not name or len(name) > 160:
            flash("Enter a supplier name of 1 to 160 characters.", "danger")
        else:
            supplier = Supplier(name=name, email=email, phone=phone, address=address)
            db.session.add(supplier)
            db.session.flush()
            record_audit("supplier.created", supplier, current_user, {}, request.remote_addr)
            db.session.commit()
            flash("Supplier added.", "success")
            return redirect(url_for("settings.suppliers"))
    suppliers_list = Supplier.query.order_by(Supplier.name).all()
    return render_template("settings/suppliers.html", suppliers=suppliers_list)


@settings_bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@roles_required("admin", "inventory_manager")
def edit_supplier(supplier_id):
    supplier = db.get_or_404(Supplier, supplier_id)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower() or None
        phone = request.form.get("phone", "").strip() or None
        address = request.form.get("address", "").strip() or None
        if not name or len(name) > 160 or (email and ("@" not in email or len(email) > 255)):
            flash("Enter a valid supplier name and email address.", "danger")
        else:
            before = {"name": supplier.name, "email": supplier.email, "phone": supplier.phone, "address": supplier.address}
            supplier.name, supplier.email, supplier.phone, supplier.address = name, email, phone, address
            record_audit("supplier.updated", supplier, current_user, {"before": before}, request.remote_addr)
            db.session.commit()
            flash("Supplier updated.", "success")
            return redirect(url_for("settings.suppliers"))
    return render_template("settings/supplier_form.html", supplier=supplier)


@settings_bp.post("/suppliers/<int:supplier_id>/toggle-active")
@roles_required("admin", "inventory_manager")
def toggle_supplier(supplier_id):
    supplier = db.get_or_404(Supplier, supplier_id)
    supplier.is_active = not supplier.is_active
    action = "supplier.activated" if supplier.is_active else "supplier.deactivated"
    record_audit(action, supplier, current_user, {}, request.remote_addr)
    db.session.commit()
    flash(f"Supplier {'activated' if supplier.is_active else 'deactivated'}.", "success")
    return redirect(url_for("settings.suppliers"))


@settings_bp.post("/suppliers/<int:supplier_id>/delete")
@roles_required("admin", "inventory_manager")
def delete_supplier(supplier_id):
    supplier = db.get_or_404(Supplier, supplier_id)
    in_use = (Product.query.filter_by(supplier_id=supplier.id).first()
              or PurchaseOrder.query.filter_by(supplier_id=supplier.id).first())
    if in_use:
        flash("This supplier is referenced by products or purchase orders. Deactivate it to retain history.", "warning")
    else:
        record_audit("supplier.deleted", supplier, current_user, {"name": supplier.name}, request.remote_addr)
        db.session.delete(supplier)
        db.session.commit()
        flash("Unused supplier deleted.", "success")
    return redirect(url_for("settings.suppliers"))


@settings_bp.route("/users", methods=["GET", "POST"])
@roles_required("admin")
def users():
    managed_role_names = ("inventory_manager", "sales_staff")
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = db.session.get(Role, request.form.get("role_id", type=int))
        if (not name or len(name) > 120 or "@" not in email or len(email) > 255
                or role is None or role.name not in managed_role_names or len(password) < 12):
            flash("Enter a valid name and email, choose Inventory Manager or Sales Staff, and use a password of at least 12 characters.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
        else:
            user = User(name=name, email=email, role=role, is_active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            record_audit("user.created", user, current_user, {"role": role.name}, request.remote_addr)
            db.session.commit()
            flash("User account created.", "success")
            return redirect(url_for("settings.users"))
    team_users = User.query.join(Role).filter(Role.name.in_(managed_role_names)).order_by(User.name).all()
    team_roles = Role.query.filter(Role.name.in_(managed_role_names)).order_by(Role.name).all()
    return render_template("settings/users.html", users=team_users, roles=team_roles)


def _team_user_or_404(user_id):
    user = db.get_or_404(User, user_id)
    if user.role.name not in {"inventory_manager", "sales_staff"}:
        abort(404)
    return user


@settings_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit_user(user_id):
    user = _team_user_or_404(user_id)
    team_roles = Role.query.filter(Role.name.in_(("inventory_manager", "sales_staff"))).order_by(Role.name).all()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = db.session.get(Role, request.form.get("role_id", type=int))
        password = request.form.get("password", "")
        duplicate = User.query.filter(User.email == email, User.id != user.id).first()
        if not name or len(name) > 120 or "@" not in email or len(email) > 255:
            flash("Enter a valid name and email address.", "danger")
        elif duplicate:
            flash("An account with that email already exists.", "danger")
        elif role is None or role.name not in {"inventory_manager", "sales_staff"}:
            flash("Choose Inventory Manager or Sales Staff.", "danger")
        elif password and len(password) < 12:
            flash("A replacement password must contain at least 12 characters.", "danger")
        else:
            before = {"name": user.name, "email": user.email, "role": user.role.name}
            user.name, user.email, user.role = name, email, role
            if password:
                user.set_password(password)
            record_audit("user.updated", user, current_user, {"before": before}, request.remote_addr)
            db.session.commit()
            flash("Team account updated.", "success")
            return redirect(url_for("settings.users"))
    return render_template("settings/user_form.html", user=user, roles=team_roles)


@settings_bp.post("/users/<int:user_id>/toggle-active")
@roles_required("admin")
def toggle_user(user_id):
    user = _team_user_or_404(user_id)
    user.is_active = not user.is_active
    action = "user.activated" if user.is_active else "user.deactivated"
    record_audit(action, user, current_user, {}, request.remote_addr)
    db.session.commit()
    flash(f"Team account {'activated' if user.is_active else 'deactivated'}.", "success")
    return redirect(url_for("settings.users"))


@settings_bp.post("/users/<int:user_id>/delete")
@roles_required("admin")
def delete_user(user_id):
    user = _team_user_or_404(user_id)
    has_history = any((
        Product.query.filter((Product.created_by_id == user.id) | (Product.updated_by_id == user.id)).first(),
        StockMovement.query.filter_by(created_by_id=user.id).first(),
        PurchaseOrder.query.filter(
            (PurchaseOrder.created_by_id == user.id)
            | (PurchaseOrder.approved_by_id == user.id)
            | (PurchaseOrder.received_by_id == user.id)
        ).first(),
        SalesOrder.query.filter(
            (SalesOrder.created_by_id == user.id)
            | (SalesOrder.completed_by_id == user.id)
        ).first(),
        AuditLog.query.filter_by(user_id=user.id).first(),
    ))
    if has_history:
        flash("This account has operational or audit history. Deactivate it to preserve the record.", "warning")
    else:
        record_audit("user.deleted", user, current_user, {"email": user.email}, request.remote_addr)
        db.session.delete(user)
        db.session.commit()
        flash("Unused team account deleted.", "success")
    return redirect(url_for("settings.users"))


@settings_bp.get("/audit")
@roles_required("admin")
def audit():
    page = AuditLog.query.outerjoin(User, AuditLog.user_id == User.id).add_columns(
        User.name, User.email,
    ).order_by(AuditLog.created_at.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=50, error_out=False,
    )
    return render_template("settings/audit.html", pagination=page)


@settings_bp.route("/warehouses", methods=["GET", "POST"])
@roles_required("admin")
def warehouses():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()
        if not name or len(name) > 120 or len(code) < 2 or len(code) > 30 or not code.replace("-", "").replace("_", "").isalnum():
            flash("Enter a warehouse name and a 2 to 30 character code using letters, digits, hyphens, or underscores.", "danger")
        elif Warehouse.query.filter_by(code=code).first():
            flash("That warehouse code is already in use.", "danger")
        else:
            warehouse = Warehouse(name=name, code=code, is_active=True)
            db.session.add(warehouse)
            db.session.flush()
            record_audit("warehouse.created", warehouse, current_user, {}, request.remote_addr)
            db.session.commit()
            flash("Warehouse added.", "success")
            return redirect(url_for("settings.warehouses"))
    return render_template("settings/warehouses.html", warehouses=Warehouse.query.order_by(Warehouse.name).all())


@settings_bp.post("/warehouses/<int:warehouse_id>/deactivate")
@roles_required("admin")
def deactivate_warehouse(warehouse_id):
    warehouse = db.get_or_404(Warehouse, warehouse_id)
    warehouse.is_active = False
    record_audit("warehouse.deactivated", warehouse, current_user, {}, request.remote_addr)
    db.session.commit()
    flash("Warehouse deactivated. Historical stock and order records are retained.", "success")
    return redirect(url_for("settings.warehouses"))