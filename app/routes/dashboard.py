from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from flask import Blueprint, render_template
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.models import Inventory, Product, PurchaseOrder, SalesOrder, StockMovement

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/")
@login_required
def index():
    today = date.today()
    start = today - timedelta(days=13)
    products = Product.query.filter_by(is_active=True).count()
    inventory_value = db.session.query(func.coalesce(func.sum(Inventory.quantity * Product.cost_price), 0)).join(Product).filter(Product.is_active.is_(True)).scalar()
    low_stock = Inventory.query.join(Product).filter(
        Product.is_active.is_(True), Inventory.quantity <= Product.reorder_level,
    ).order_by(Product.name).limit(8).all()
    sales_query = SalesOrder.query.filter_by(status="completed")
    if current_user.role.name == "sales_staff":
        sales_query = sales_query.filter_by(created_by_id=current_user.id)
    sales = sales_query.filter(
        SalesOrder.completed_at >= datetime.combine(start, time.min, tzinfo=timezone.utc),
    ).order_by(SalesOrder.completed_at).all()
    purchases = PurchaseOrder.query.filter_by(status="received").filter(
        PurchaseOrder.received_at >= datetime.combine(start, time.min, tzinfo=timezone.utc),
    ).all()
    movements = StockMovement.query.filter(
        StockMovement.created_at >= datetime.combine(start, time.min, tzinfo=timezone.utc),
    ).all()
    sales_by_day = {start + timedelta(days=offset): Decimal("0.00") for offset in range(14)}
    inbound_by_day = {day: 0 for day in sales_by_day}
    outbound_by_day = {day: 0 for day in sales_by_day}
    for order in sales:
        order_day = order.completed_at.date()
        if order_day in sales_by_day:
            sales_by_day[order_day] += order.total_amount
    for movement in movements:
        movement_day = movement.created_at.date()
        if movement_day in inbound_by_day and movement.quantity_delta > 0:
            inbound_by_day[movement_day] += movement.quantity_delta
        elif movement_day in outbound_by_day and movement.quantity_delta < 0:
            outbound_by_day[movement_day] += abs(movement.quantity_delta)
    sales_total = sum((order.total_amount for order in sales), Decimal("0.00"))
    purchases_total = sum((order.total_amount for order in purchases), Decimal("0.00"))
    return render_template(
        "dashboard/index.html", product_count=products, inventory_value=inventory_value or 0,
        can_view_costs=current_user.role.name in {"admin", "inventory_manager"},
        low_stock=low_stock, sales_total=sales_total, purchases_total=purchases_total,
        chart_labels=[day.strftime("%b %d") for day in sales_by_day],
        chart_values=[float(amount) for amount in sales_by_day.values()],
        has_sales=any(sales_by_day.values()),
        movement_in_values=list(inbound_by_day.values()),
        movement_out_values=list(outbound_by_day.values()),
        has_movements=any(inbound_by_day.values()) or any(outbound_by_day.values()),
    )