"""Affiliate partner administration entry point."""

from flask import Blueprint, render_template

from ..auth import login_required


bp = Blueprint("admin_affiliates", __name__, url_prefix="/admin/affiliates")


@bp.get("/")
@login_required
def index():
    """Render the protected affiliate administration landing page."""
    return render_template("admin/affiliates/index.html")
