from main import create_app
from main.email import mail

app = create_app()
mail.init_app(app)

if __name__ == '__main__':
    app.run()
