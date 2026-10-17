import logging
import os
from logging.config import dictConfig
from decimal import Decimal

import click
from flask import Flask, jsonify, render_template, request
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from config import config_by_name

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


def create_app(config_name=None, test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    config_name = config_name or os.getenv("FLASK_ENV", "development")
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))
    if test_config:
        app.config.update(test_config)
    if config_name == "production" and (not app.config.get("SECRET_KEY") or not app.config.get("SQLALCHEMY_DATABASE_URI")):
        raise RuntimeError("Production requires SECRET_KEY and DATABASE_URL environment variables.")
    os.makedirs(app.instance_path, exist_ok=True)

    dictConfig({
        "version": 1,
        "formatters": {"default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "default"}},
        "root": {"level": app.config.get("LOG_LEVEL", "INFO"), "handlers": ["console"]},
    })
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    from app.models import AuditLog, Category, Inventory, Product, Role, StockMovement, Supplier, User, Warehouse
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.inventory import inventory_bp
    from app.routes.purchases import purchases_bp
    from app.routes.products import products_bp
    from app.routes.reports import reports_bp
    from app.routes.sales import sales_bp
    from app.routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(settings_bp)

    @app.errorhandler(400)
    def bad_request(error):
        if app.config.get("TESTING") or request.accept_mimetypes.best == "application/json":
            return jsonify(error="bad_request", message="The request could not be processed."), 400
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(error):
        if request.accept_mimetypes.best == "application/json":
            return jsonify(error="forbidden", message="You do not have permission to perform this action."), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        if request.accept_mimetypes.best == "application/json":
            return jsonify(error="not_found", message="The requested resource was not found."), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled application error", exc_info=error)
        if request.accept_mimetypes.best == "application/json":
            return jsonify(error="internal_error", message="An unexpected error occurred."), 500
        return render_template("errors/500.html"), 500

    @app.cli.command("init-db")
    def init_db():
        """Create tables and seed the built-in roles and default warehouse."""
        db.create_all()
        for role_name in ("admin", "inventory_manager", "sales_staff"):
            if not Role.query.filter_by(name=role_name).first():
                db.session.add(Role(name=role_name))
        if not Warehouse.query.filter_by(code="MAIN").first():
            db.session.add(Warehouse(name="Main Warehouse", code="MAIN"))
        db.session.commit()
        click.echo("Database initialized. Create an administrator with `flask create-admin`.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Full name")
    @click.password_option()
    def create_admin(email, name, password):
        """Create an administrator account without hard-coded credentials."""
        if User.query.filter_by(email=email.strip().lower()).first():
            raise click.ClickException("An account with that email already exists.")
        role = Role.query.filter_by(name="admin").first()
        if role is None:
            raise click.ClickException("Run `flask init-db` first.")
        if len(password) < 12:
            raise click.ClickException("Use a password with at least 12 characters.")
        user = User(name=name.strip(), email=email.strip().lower(), role=role, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrator {email} created.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add sample catalog, supplier, and opening stock for development."""
        admin = User.query.filter_by(email="admin@example.com").first()
        if admin is None:
            role = Role.query.filter_by(name="admin").first()
            demo_password = os.getenv("DEMO_ADMIN_PASSWORD")
            if not demo_password:
                raise click.ClickException("Set DEMO_ADMIN_PASSWORD before seeding the demo account.")
            if len(demo_password) < 12:
                raise click.ClickException("DEMO_ADMIN_PASSWORD must contain at least 12 characters.")
            admin = User(name="Demo Administrator", email="admin@example.com", role=role, is_active=True)
            admin.set_password(demo_password)
            db.session.add(admin)
        category = Category.query.filter_by(name="Office Supplies").first()
        if category is None:
            category = Category(name="Office Supplies", description="Everyday workplace supplies")
            db.session.add(category)
        supplier = Supplier.query.filter_by(name="Northstar Wholesale").first()
        if supplier is None:
            supplier = Supplier(name="Northstar Wholesale", email="orders@example.com", is_active=True)
            db.session.add(supplier)
        warehouse = Warehouse.query.filter_by(code="MAIN").first()
        db.session.flush()
        if Product.query.filter_by(sku="DEMO-PEN-001").first() is None:
            product = Product(sku="DEMO-PEN-001", name="Fine-tip black pen", brand="Northstar",
                              category=category, supplier=supplier, selling_price=Decimal("2.49"),
                              cost_price=Decimal("0.85"), reorder_level=15, created_by_id=admin.id)
            db.session.add(product)
            db.session.flush()
            db.session.add(Inventory(product=product, warehouse=warehouse, quantity=48))
            db.session.add(StockMovement(
                product=product, warehouse=warehouse, movement_type="adjustment", quantity_delta=48,
                reference="DEMO-OPENING", note="Development sample opening balance", created_by_id=admin.id,
            ))
        db.session.commit()
        click.echo("Demo records created. Sign in with admin@example.com and DEMO_ADMIN_PASSWORD.")

    return app