# DESCRIPTION: HELPER FUNCTIONS FOR STORE.PY
# TABLE OF CONTENTS
# get_images()
# process_cart()
# process_cart_total()
# process_checkout()


from flask import session, g
from main.db import get_db
import os

basedir = os.path.abspath(os.path.dirname(__file__))
#loop through files in static/products and return a list of related images
def get_images(image):
    images = []
    filename, file_extension = os.path.splitext(image)
    for file in os.listdir(os.path.join(basedir, r'static/products')):
        if os.path.splitext(os.path.split(image)[1])[0] in file and file.endswith(file_extension):
             images.append(os.path.join(os.path.split(image)[0],file))
        else:
            print(file, os.path.splitext(os.path.split(image)[1])[0])
    return images

#uses session value to query and build a list with dictionaries; [{sqliteObject:qty}]
def process_cart():
    cart = session.get('cart')
    cart_items = []
    db = get_db()
    if 'cart' in session:
        for d in cart:
            for k,v in d.items():
                item = db.execute("select * from item where alt_sku = ?", (k,)).fetchone()
                cart_items.append({item:v})
        return cart_items
    else:
        return None

#uses session value to generate total
def process_cart_total():
    total_price = 0
    cart_items = process_cart()
    if cart_items is None:
        return None
    else:
        for i in cart_items:
            for k, v in i.items():
                total_price += k['price'] * v
        return total_price

#update consumer location if not exist and insert order_items as well as set session['email_block']
def process_checkout(fname, lname, address1, address2, city, state, country, postal_code, phone, email):
    db = get_db()
    checkout_items = process_cart()
    total_price = process_cart_total()

    user_id = g.user['user_id'] if g.user is not None else None
    db_location = db.execute(
        "select * from location l join consumer c \
        on l.consumer_id = c.consumer_id where c.user_id = ?",
        (user_id,)
    ).fetchone()
    location = db_location if (db_location is not None) else None

    if location is None:
        # create a consumer record
        user_reference = g.user['user_id'] if g.user is not None else None
        db.execute(
            "insert into consumer values (null, 856, ?, ?, ?, ?, 'Consumer', ?)",
            (user_reference, fname, lname, phone, email, )
        )
        # query specific consumer for consumer id
        consumer = db.execute(
            "select * from consumer where user_id = ?",
            (user_id,)
        ).fetchone()
        consumer_guest = db.execute(
            "select last_insert_rowid() consumer_id"
        ).fetchone()
        consumer = consumer if consumer is not None else consumer_guest
        # create location record
        db.execute(
            "insert into location values (null, 856, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)",
            (consumer['consumer_id'], fname, lname, address1,
             address2, city, state, country, postal_code,)
        )
        last_order = db.execute(
            "select * from 'order' where org_id = 856 order by order_id DESC limit 1"
        ).fetchone()
        location = db.execute(
            "select * from location l join consumer c on l.consumer_id = c.consumer_id where c.consumer_id = ?",
            (consumer['consumer_id'],)
        ).fetchone()
        db.execute(
            "insert into 'order' values (null, ?, 856, ?, 'CC', CURRENT_DATE, DATE('now', '+3 day'), null, null, CURRENT_TIMESTAMP)",
            (int(last_order['cust_po']) + 1, location['loc_id'])
        )
        order_id = db.execute(
            "select last_insert_rowid() order_id"
        ).fetchone()['order_id']
        for i in checkout_items:
            for k, v in i.items():
                db.execute(
                    "insert into order_item values(?, ?, ?, ?)",
                    (order_id, k['item_id'], v, k['price'],)
                )
        order_items = db.execute(
            "select o.order_id order_id, o.qty qty, o.unit_price price, i.alt_sku sku, i.brand brand, i.model model, i.img img from order_item o join item i on o.item_id = i.item_id where o.order_id = ?",
            (order_id,)
        ).fetchall()
        db.commit()
        session['email_block'] = {'order_id': order_id, 'fname': fname,
                                  'lname': lname, 'total_price': total_price, 'email': email}
        session.pop('cart')
    # if location id exists, insert into order and order_item
    else:
        # get last order id to find last cust po for sinphyudaw orders
        last_order = db.execute(
            "select * from 'order' where org_id = 856 order by order_id DESC limit 1"
        ).fetchone()
        # create order record
        db.execute(
            "insert into 'order' values (null, ?, 856, ?, 'CC', CURRENT_DATE, DATE('now', '+3 day'), null, null, CURRENT_TIMESTAMP)",
            (int(last_order['cust_po']) + 1, location['loc_id'])
        )
        # get last order_id to reference in order_item
        order_id = db.execute(
            "select last_insert_rowid() order_id"
        ).fetchone()['order_id']
        # create an order_item record for each item in cart
        for i in checkout_items:
            for k, v in i.items():
                db.execute(
                    "insert into order_item values (?, ?, ?, ?)",
                    (order_id, k['item_id'], v, k['price'],)
                )
        order_items = db.execute(
            "select o.order_id order_id, o.qty qty, o.unit_price price, i.alt_sku sku, i.brand brand, i.model model, \
            i.img img from order_item o join item i on o.item_id = i.item_id where o.order_id = ?",
            (order_id,)
        ).fetchall()
        db.commit()
        session['email_block'] = {'order_id': order_id, 'fname': fname,
                                  'lname': lname, 'total_price': total_price, 'email': email}
        session.pop('cart')
