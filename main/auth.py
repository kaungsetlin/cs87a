# DESCRIPTION: LOGIC FOR VIEWS RELATED TO USER AUTHENTICATION
# TABLE OF CONTENTS:
# def register()
# def login()
# def load_logged_in_user()
# def check_verified()
# def logout()
# def login_required()
# def admin_login_required()
# def generate_confirmation_token()
# def confirm_password_token()
# def confirm()
# def unconfirmed()
# def resend_confirmation()
# def change_password()
# def password_reset_request()
# def password_reset()

import functools
from flask import (Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app)
from werkzeug.security import check_password_hash, generate_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from main.db import get_db
from .email import send_email

bp = Blueprint('auth', __name__, url_prefix='/auth')

#register page
@bp.route('/register', methods = ('GET', 'POST'))
def register():
    app = current_app._get_current_object()
    if request.method == 'POST':
        username = request.form['username'].lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        db = get_db()
        error = None

        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'
        elif password != confirm_password:
            error = 'Passwords do not match.'
        if error is None:
            try:
                db.execute(
                    "insert into user values (null, ?, ?, CURRENT_TIMESTAMP, 3, 0)",
                    (username, generate_password_hash(password),)
                )
                #save changes in database
                db.commit()
                #get last user id
                last_user = db.execute(
                    "select last_insert_rowid() user_id",
                ).fetchone()
                user = db.execute(
                    "select * from user where user_id = ?",
                    (last_user['user_id'],)
                ).fetchone()
            except db.IntegrityError:
                error = f"User {username} is already registered."
            else:
                #send confirmation email
                token = generate_confirmation_token(user)
                send_email(user['username'], ' Confirm Your Account', 'auth/email/confirm', user = user, token = token)

                #send email to admin that a user joined
                if app.config['ADMIN']:
                    send_email(app.config['ADMIN'], ' New User', 'mail/new_user', username = username)

                flash(f"A confirmation email has been sent to {username}. Please verify to log in.")
                return redirect(url_for('auth.login'))
        flash(error)
    return render_template('auth/register.html')

#log in page
@bp.route('/login', methods = ('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute(
            'select * from user where username = ?', (username,)
        ).fetchone()


        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'
        if error is None:
            session.clear()
            session['user_id'] = user['user_id']
            if 'token' in session:
                auth_confirm = url_for('auth.confirm', token = session.get('token'))
                return redirect(auth_confirm)

            return redirect(url_for('store.index'))
        flash(error)
    return render_template('auth/login.html')

#set g.user from session user before all requests
@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    db = get_db()
    consumer = db.execute(
        "select * from consumer where user_id = ?",
        (user_id,)
    ).fetchone()
    if user_id is None:
        g.user = None
    else:
        no_consumer = get_db().execute(
            "select * from user where user_id = ?",
            (user_id,)
        ).fetchone()
        yes_consumer = get_db().execute(
            "select user.user_id user_id, verified, username, role_id, fname, lname, phone, email, ship_fname, ship_lname, address1, address2, city, state, country, postal_code from user join consumer on user.user_id = consumer.user_id join location on consumer.consumer_id = location.consumer_id where user.user_id = ?",
            (user_id,)
        ).fetchone()
        #query base on whether there is consumer record or not
        g.user = no_consumer if consumer is None else yes_consumer

@bp.before_app_request
def check_verified():
    if g.user is not None and g.user['verified'] == 0 and request.blueprint != 'auth' and request.endpoint != 'static':
        return redirect(url_for('auth.unconfirmed'))



#log out url route
@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('store.index'))

#decorator that requires users to be logged in
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

#decorator that requires users to be admin and logged in
def admin_login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash('Permission denied. Please log in first.')
            return redirect(url_for('auth.login'))
        elif g.user['role_id'] != 1:
            session.clear()
            flash('Permission denied. You are not an admin.')
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

#generate an account confirmation token
def generate_confirmation_token(self, expiration = 3600):
    s = Serializer(current_app.config['SECRET_KEY'], expiration)
    return s.dumps({'confirm': self['user_id']}).decode('utf-8')

def confirm_token(self, token):
    s = Serializer(current_app.config['SECRET_KEY'])
    try:
        data = s.loads(token.encode('utf-8'))
    except:
        return False
    if data.get('confirm') != self['user_id']:
        return False
    db = get_db()
    db.execute(
        "update user set verified = 1 where user_id = ?",
        (self['user_id'],)
    )
    return True


def confirm_password_token(password, self, token):
    s = Serializer(current_app.config['SECRET_KEY'])
    try:
        data = s.loads(token.encode('utf-8'))
    except:
        return False
    if data.get('confirm') != self['user_id']:
        return False
    db = get_db()
    db.execute(
        "update user set password = ? where user_id = ?",
        (generate_password_hash(password), self['user_id'],)
    )
    return True

#directed to here from email link
@bp.route('/confirm/<token>')
def confirm(token):
    session['token'] = token
    if g.user is None:
        return redirect(url_for('auth.login'))
    elif g.user['verified'] == 1:
        session.pop('token')
        flash('Your account is already verified.')
        return redirect(url_for('store.index'))
    if confirm_token(g.user, token):
        db = get_db()
        db.commit()
        flash('Thank you for verifying your account.')
    else:
        flash('The confirmation link is invalid or has expired.')
    return redirect(url_for('store.index'))

@bp.route('/unconfirmed')
def unconfirmed():
    if g.user['verified'] == 1:
        return redirect(url_for('store.index'))
    return render_template('auth/unconfirmed.html')

@bp.route('/confirm')
@login_required
def resend_confirmation():
    token = generate_confirmation_token(g.user,)
    send_email(g.user['username'], ' Confirm Your Account', 'auth/email/confirm', user = g.user, token = token)
    flash('A new confirmation email has been sent to your email.')
    return redirect(url_for('store.index'))


@bp.route('/change_password', methods = ('POST', 'GET'))
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form.get('current_password')
        new = request.form.get('new_password')
        db = get_db()
        error = None
        password = db.execute(
            "select password from user where user_id = ?",
            (g.user['user_id'],)
        ).fetchone()['password']
        if not check_password_hash(password, current):
            error = 'Invalid password.'
        elif current == new:
            error = 'It seems you remember your password.'
        else:
            db.execute(
                "update user set password = ? where user_id = ?",
                (generate_password_hash(new), g.user['user_id'],)
            )
            db.commit()
            flash('Your password has been update successfully.')
            return redirect(url_for('store.index'))
        flash(error)
    return render_template('auth/change_password.html')


@bp.route('/reset', methods = ('GET', 'POST'))
def password_reset_request():
    db = get_db()
    error = None
    if request.method == 'POST':
        email = request.form.get('email').lower()
        user = db.execute(
            "select user_id, username, password from user where username = ?",
            (email,)
        ).fetchone()
        if user:
            token = generate_confirmation_token(user)
            session['request_user'] = user['user_id']
            send_email(user['username'], ' Reset Your Password', 'auth/email/reset_password', user = user, token = token)
            flash(f"An email with instructions to reset your password has been sent to {user['username']}.")
        else:
            flash('Invalid email.')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html')

@bp.route('/reset/<token>', methods = ('GET', 'POST'))
def password_reset(token):
    db = get_db()
    if request.method == 'POST':
        if session.get('request_user') is not None:
            user = db.execute(
                "select * from user where user_id = ?",
                (session.get('request_user'),)
            ).fetchone()
        else:
            flash('An unknown error has occured. Please contact Sinphyudaw for support.')
        new = request.form.get('new')
        confirm = request.form.get('confirm')
        if new != confirm:
            flash('Passwords do not match.')
        elif confirm_password_token(new, user, token):
            db.commit()
            session.pop('request_user')
            flash('Your password has been reset.')
            return redirect(url_for('auth.login'))
        else:
            flash('An error has occured. Please contact Sinphyudaw for support.')
            return redirect(url_for('auth.login'))
    return render_template('auth/reset_password_token.html')
