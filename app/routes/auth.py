from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_next(target):
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme or "\\" in target or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, is_active=True).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get("remember") == "on")
            return redirect(_safe_next(request.args.get("next")) or url_for("dashboard.index"))
        flash("Email or password is incorrect.", "danger")
    return render_template("auth/login.html")


@auth_bp.post("/logout")
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))