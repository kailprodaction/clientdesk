"""Фабрика приложения ClientDesk."""
import secrets

from dotenv import load_dotenv
from flask import Flask, g, session

from .config import Config
from .extensions import db

load_dotenv()


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    from . import models  # noqa: F401  (регистрация моделей)

    with app.app_context():
        db.create_all()

    # --- Простейший CSRF-токен для POST-форм (Flask-WTF из спеки заменён лёгким аналогом) ---
    @app.before_request
    def ensure_csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(24)

    @app.context_processor
    def inject_globals():
        from .auth.routes import current_user

        return {"csrf_token": session.get("csrf_token"), "current_user": current_user()}

    # --- Блюпринты ---
    from .auth.routes import bp as auth_bp
    from .projects.routes import bp as projects_bp
    from .comments.routes import bp as comments_bp
    from .ai.routes import bp as ai_bp
    from .client.routes import bp as client_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(comments_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(client_bp)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app
