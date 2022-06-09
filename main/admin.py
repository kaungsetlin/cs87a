# DESCRIPTION: LOGIC FOR ADMIN VIEWS
# TABLE OF CONTENTS:
# def admin()
# def table()

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from main.db import get_db
from main.auth import login_required, admin_login_required

bp = Blueprint('admin', __name__, url_prefix='/admin')

#admin home view
@bp.route('/')
@admin_login_required
def admin():
    layout = {
        'dictionaries': ['attr1', 'attr2', 'attr3', 'brand', 'category', 'credit_term', 'price_group', 'range', 'range_attr3', 'ship_method', ],
        'organizations': ['organization', 'location', 'consumer', ],
        'products': ['model', 'item', ],
        'sales': ['order', 'order_item', 'invoice', 'invoice_item', 'return' ,'credit_memo', 'payment'],
        'production': ['vendor', 'vendor_location', 'po', 'po_item', 'receiver', ],
        'users': ['role', 'user', ],
    }
    db = get_db()
    tables = db.execute(
        "select tbl_name from sqlite_master where type = 'table' order by tbl_name"
    ).fetchall()
    return render_template('admin/admin.html', tables = tables, layout = layout)

#specific table view; need more secure method
@bp.route('/<table>')
@admin_login_required
def table(table):
    db = get_db()
    fields = db.execute(
        f"pragma table_info('{table}')"
    ).fetchall()
    records = db.execute(
        f"select * from '{table}'"
    ).fetchall()
    return render_template('admin/table.html', table = table, fields = fields, records = records)
