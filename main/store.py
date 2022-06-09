# DESCRIPTION: LOGIC FOR VIEWS RELATED TO THE STORE
# TABLE OF CONTENTS
# def index()
# def store()
# def search()
# def detail(model)
# def support()
# def cart()
# def checkout()
# def payment()
# def success()
# def cancel()
# def account()
# def orders()
# def test()
# def cart_delete()

from flask import (Blueprint, flash, g, redirect,
                   render_template, request, url_for, abort, session)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import abort
from main.auth import login_required, admin_login_required
from main.db import get_db
from .email import send_email
from .utils import process_cart, process_cart_total, get_images, process_checkout
import math
import os
import stripe

bp = Blueprint('store', __name__)

@bp.route('/')
def index():
    db = get_db()
    cart_items = process_cart()
    total_price = process_cart_total()
    orders = None
    if g.user:
        orders = db.execute(
            "select * from 'order' where loc_id = (select loc_id from location where consumer_id = (select consumer_id from consumer where user_id = ?)) order by created desc limit 2",
            (g.user['user_id'],)
        ).fetchall()
    new_products = db.execute(
        "select brand, i.model model, m.name name, min(price) min, max(price) max, range, m.model_img img  \
        from item i join model m on i.model = m.model group by i.model order by created DESC limit 8").fetchall()
    top_products = db.execute(
        "select brand, i.model model, m.name name, min(price) min, max(price) max, range, m.model_img img from item i \
        join model m on i.model = m.model \
        join order_item o on i.item_id = o.item_id where i.item_id in \
        (select item_id from order_item group by item_id order by count(item_id) desc) \
        group by i.model order by count(o.item_id) desc limit 8").fetchall()

    return render_template('store/index.html', cart_items=cart_items, total_price=total_price, new_products=new_products, top_products=top_products, orders=orders)


@bp.route('/store')
def store():
    # paginate
    db = get_db()
    page = request.args.get('page', 1, type=int)
    limit = 10
    offset = (page - 1) * limit
    count = db.execute(
        "select count(*) over() count from item group by model"
    ).fetchone()['count']
    pages = round(count / limit)
    models = db.execute(
        "select brand, i.model model, m.name name, min(price) min, \
        max(price) max, range, m.model_img img  from item i join \
        model m on i.model = m.model group by i.model order by \
        created DESC limit ? offset ?", (limit, offset, )
    ).fetchall()
    return render_template('store/store.html', models=models, page=page, pages=pages)


@bp.route('/search')
def search():
    query = request.args.get('query', None)
    query = query.translate(str.maketrans({'"': r'""'}))
    error = None
    db = get_db()
    results = None
    if query is None:
        error = "Empty search input."
    else:
        results = db.execute(
            "select s.model model, s.model_name name, min(i.price) min, \
            max(i.price) max, i.range range from store s join item i on \
            s.alt_sku = i.alt_sku where store match ? group by s.model order by rank",
            (f"\"{query}\"",)
        ).fetchall()

    return render_template('store/search.html', results=results, query=query)

@bp.route('/store/<string:model>', methods=('GET', 'POST'))
def detail(model):
    # setup
    db = get_db()
    error = None

    # remove session['sku'] if user leaves page for specific model
    if session.get('sku') is not None and session.get('sku')['model'] != model:
        session.pop('sku')

    # MODEL available: model, name, model_img
    db_model = db.execute(
        "select distinct m.model model, m.name name, model_img, i.brand brand, \
        i.category category from model m join item i on m.model = i.model \
        where m.model = ?", (model,)).fetchone()
    # if model does not exist
    if db_model is None:
        abort(404)

    # COLOR available: name Iso Bars, color 05
    db_colors = db.execute(
        "select distinct a.name name, a.attr1 color from item i join attr1 a \
        on i.attr1 = a.attr1 where model = ? order by a.attr1", (model,)).fetchall()

    # GRAPHIC e.g. {'05':[<sqlite_object>]} available are name, graphic, img
    db_graphics = {}
    for i in db_colors:
        db_graphics[i['color']] = db.execute(
            "select distinct a.name name, a.attr2 graphic, i.img img from \
            item i join attr2 a on i.attr2 = a.attr2 where model = ? and \
            attr1 = ?", (model, i['color'],)).fetchall()

    # SIZE available: size 21, name X Small
    db_sizes = db.execute(
        "select distinct r.attr3 size, a.name name from item i \
        join range_attr3 r on i.range = r.range join attr3 a on \
        r.attr3 = a.attr3 where model = ? order by r.attr3", (model,)).fetchall()
    # return f"{db_colors[0]['color']} {}"
    # checks if user has chosen anything; if not, give default sku
    sku = session.get('sku') if session.get('sku') else \
        db.execute(
        "select i.model model, i.img img, i.alt_sku sku, \
        i.attr1 attr1, i.attr2 attr2, i.attr3 attr3, \
        a1.name color, a2.name graphic, a3.name size from item i\
        join attr1 a1 on i.attr1 = a1.attr1 \
        join attr2 a2 on i.attr2 = a2.attr2 \
        join attr3 a3 on i.attr3 = a3.attr3 \
        where i.model = ? and i.attr1 = ? and i.attr2 = ? and i.attr3 = ?",
        (model, db_colors[0]['color'],
         db_graphics[db_colors[0]['color']][0]['graphic'],
         db_sizes[0]['size'])).fetchone()
    if sku is not None:
        session['sku'] = {'model': sku['model'], 'attr1': sku['attr1'],
                        'attr2': sku['attr2'], 'attr3': sku['attr3'],
                         'color': sku['color'], 'graphic': sku['graphic'],
                         'size': sku['size'], 'img': sku['img'], 'sku': sku['sku']}
    else:
        error = 'Item is invalid or out of stock'

    if request.method == 'POST':
        color = request.form.get('color')
        graphic = request.form.get('graphic')
        size = request.form.get('size')
        quantity = int(request.form.get('quantity'))

        if color is not None and graphic is not None and size is not None:
            session['color'] = color
            graphics_sqlite = db.execute(
                'select distinct attr2 from item where model = ? and attr1 = ?', (model, color)).fetchall()
            graphics = []
            for i in graphics_sqlite:
                graphics.append(i['attr2'])

            # if color has changed update graphics
            session['graphic'] = graphic if session.get('color') != color \
                or graphic in graphics else db_graphics[color][0]['graphic']

            session['size'] = size
            sku = db.execute(
                "select i.model model, i.img img, i.alt_sku sku, \
                i.attr1 attr1, i.attr2 attr2, i.attr3 attr3, \
                a1.name color, a2.name graphic, a3.name size from item i\
                join attr1 a1 on i.attr1 = a1.attr1 \
                join attr2 a2 on i.attr2 = a2.attr2 \
                join attr3 a3 on i.attr3 = a3.attr3 \
                where i.model = ? and i.attr1 = ? and i.attr2 = ? and i.attr3 = ?",
                (model, session.get('color'), session.get('graphic'), session.get('size'),)).fetchone()
            # return f"{sku} {model} {color} {graphic} {size}"
            if sku is not None:
                session['sku'] = {'model': sku['model'], 'attr1': sku['attr1'], 'attr2': sku['attr2'], 'attr3': sku['attr3'],
                                  'color': sku['color'], 'graphic': sku['graphic'], 'size': sku['size'],
                                  'img': sku['img'], 'sku': sku['sku']}
            else:
                error = "Item is invalid or currently out of stock."

        # redirect to cart or checkout
        if request.form.get('action') == 'Add to Cart':
            flash(cart_processor(session.get('sku')[
                  'sku'], session.get('quantity', quantity)))
            redirect(url_for('store.detail', model=model))
        if request.form.get('action') == 'Checkout':
            cart_processor(session.get('sku')['sku'], quantity)
            return redirect(url_for('store.checkout'))

        flash(error)
        return redirect(url_for('store.detail', model=model))
    # return f"{sku['attr1']}"
    return render_template('store/detail_v2.html', db_model=db_model, \
                            db_colors=db_colors, db_graphics=db_graphics, \
                            db_sizes=db_sizes, sku=session.get('sku'))


def cart_processor(sku, quantity):
    """add specific sku and submitted quantity to session['cart']"""
    error = None
    # check if user has started a session for cart
    if 'cart' in session:
        if not any(sku in d for d in session['cart']):
            session['cart'].append({sku: quantity})
            error = 'Item is added to cart.'
        elif any(sku in d for d in session['cart']):
            error = 'Item is already added to cart.'
            for d in session['cart']:
                if sku in d:
                    d.update({sku: quantity})
        return error
    else:
        session['cart'] = [{sku: quantity}]
        error = 'Item is added to cart.'
        return error


@bp.route('/support')
def support():
    flash("Server logic not added yet, only HTML and CSS for now.")
    return render_template('store/support.html')


@bp.route('/cart', methods=('GET', 'POST'))
def cart():
    cart_items = process_cart()
    total_price = process_cart_total()
    error = None
    if request.method == 'POST':
        if request.form.get('action') == 'Checkout':
            return redirect(url_for('store.checkout'))
        sku = request.form.get('sku', None)
        qty = int(request.form.get('qty'))

        if any(sku in d for d in session.get('cart')):
            for d in session['cart']:
                if sku in d:
                    d.update({sku: qty})
                    flash(f"Quantity for {sku} is updated.")

        return redirect(url_for('store.cart'))
    return render_template('store/cart.html', cart_items=cart_items, total_price=total_price)


@bp.route('/checkout', methods=('GET', 'POST'))
def checkout():
    checkout_items = process_cart()
    total_price = process_cart_total()
    return render_template('store/checkout.html', checkout_items=checkout_items, total_price=total_price,)


@bp.route('/payment', methods=['POST'])
def payment():
    db = get_db()
    fname = request.form['fname']
    lname = None if not request.form['lname'] else request.form['lname']
    address1 = request.form['address1']
    address2 = request.form.get('address2', None)
    city = request.form['city']
    state = request.form.get('state', None)
    country = request.form['country']
    postal_code = request.form['postal_code']
    email = request.form['email']
    phone = request.form['phone']
    fname = request.form['fname']
    term = request.form.getlist('term')

    process_checkout(fname, lname, address1, address2, city, state, country, postal_code, phone, email)

    db_order_items = db.execute("select o.qty qty, o.unit_price price, i.brand, \
                                m.name model, a1.name color, a2.name graphic, a3.name size from order_item o \
                                join item i on o.item_id = i.item_id \
                                join model m on i.model = m.model \
                                join attr1 a1 on i.attr1 = a1.attr1 \
                                join attr2 a2 on i.attr2 = a2.attr2 \
                                join attr3 a3 on i.attr3 = a3.attr3 where o.order_id = ?",
                                (session.get('email_block')['order_id'], )).fetchall()
    if db_order_items is None:
        abort(404)

    line_items = []
    for order_item in db_order_items:
        line_item = {'price_data': {'product_data': {'name': order_item['brand'] + ' ' +
                                                     order_item['model'] + ' ' +
                                                     order_item['color'] + ' ' +
                                                     order_item['graphic'] + ' ' +
                                                     order_item['size'], },
                                    'unit_amount': int(float(order_item['price']) * 100),
                                    'currency': 'usd', },
                     'quantity': order_item['qty'], }
        line_items.append(line_item)

    checkout_session = stripe.checkout.Session.create(
        line_items=line_items,
        payment_method_types=['card'],
        mode='payment',
        success_url=request.host_url + 'order/success',
        cancel_url=request.host_url + 'order/cancel',
    )
    return redirect(checkout_session.url)


@bp.route('/order/success')
def success():
    db = get_db()
    order_id = session.get('email_block')['order_id']
    fname = session.get('email_block')['fname']
    lname = session.get('email_block')['lname']
    email = session.get('email_block')['email']
    total_price = session.get('email_block')['total_price']
    order_items = db.execute(
        "select o.order_id order_id, o.qty qty, o.unit_price price, i.alt_sku sku, i.brand brand, i.model model, \
        i.img img from order_item o join item i on o.item_id = i.item_id where o.order_id = ?",
        (order_id,)
    ).fetchall()

    send_email(email, f' Order #{order_id} Confirmed', 'store/email/order_confirmation',
               order_id=order_id, order_items=order_items, fname=fname, lname=lname, total_price=total_price)
    flash('An email with your order confirmation will arrive shortly.', 'success')
    if session.get('email_block') is not None:
        session.pop('email_block')
    return render_template('store/success.html')


@bp.route('/order/cancel')
def cancel():
    db = get_db()
    order_id = session.get('email_block')['order_id']
    # delete order and associated items
    db.execute("delete from order_item where order_id = ?", (order_id,))
    db.execute("delete from 'order' where order_id = ?", (order_id,))
    flash('Your order has been cancelled.')
    if session.get('email_block') is not None:
        session.pop('email_block')
    return render_template('store/cancel.html')


@bp.route('/account')
@login_required
def account():
    return render_template('store/account.html')


@bp.route('/account/orders')
@login_required
def orders():
    orders = {}
    error = None
    db = get_db()
    order_ids = db.execute(
        "select * from 'order' o join location l on o.loc_id = l.loc_id \
        join consumer c on l.consumer_id = c.consumer_id join user u \
        on c.user_id = u.user_id where u.user_id = ? order by created desc;",
        (g.user['user_id'],)
    ).fetchall()
    if order_ids is None:
        error = 'No orders found...'
    if error is None:
        # loop orders from user which are sqliteobjects
        for order_id in order_ids:
            order_item = db.execute(
                "select * from order_item oi join 'order' o on \
                oi.order_id = o.order_id join item i on \
                oi.item_id = i.item_id where o.order_id = ?",
                (order_id['order_id'],)
            ).fetchall()
            # add to orders dictionary
            orders.update({order_id: order_item})
    flash(error)
    return render_template('store/orders.html', orders=orders)

# place to test functions


@bp.route('/test')
@admin_login_required
def test():
    flash('A place to test ideas.')
    return render_template('store/test.html')


@bp.route('/cart')
def cart_delete():
    sku = request.args.get('sku')
    error = None
    # loop session to see if sku is in any dictinary object within it
    for index, i in enumerate(session['cart']):
        if sku in i:
            session['cart'].remove(session['cart'][index])
            error = 'Item is removed from cart'
    flash(error)
    return redirect(url_for('store.cart'))
