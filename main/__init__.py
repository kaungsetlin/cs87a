# DESCRIPTION: APPLICATION FACTORY AND INTIALIZE EXTENSIONS

import os, stripe
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

def create_app(test_config = None):
    app = Flask(__name__, instance_relative_config=True)
    app.config['SECRET_KEY'] = '50c8861b827d91e8fe052e8ee3ed568f'
    app.config['DATABASE'] = os.path.join(app.instance_path, 'main.sqlite')
    app.config['MAIL_SERVER'] = 'smtp.sendgrid.net'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = None
    app.config['MAIL_PASSWORD'] = None
    app.config['MAIL_DEFAULT_SENDER'] = None
    app.config['ADMIN'] = None
    stripe.api_key = None

    #initialize database
    from . import db
    db.init_app(app)

    #initialize mail
    from . import email
    email.mail.init_app(app)

    #register blueprint for auth module
    from . import auth
    app.register_blueprint(auth.bp)

    #register blueprint for store module
    from . import store
    app.register_blueprint(store.bp)
    app.add_url_rule('/', endpoint='index')
    app.jinja_env.globals.update(get_images=store.get_images)

    #register blueprint for admin module
    from . import admin
    app.register_blueprint(admin.bp)

    return app
