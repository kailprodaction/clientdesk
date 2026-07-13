"""Регистрация, вход, выход. Один пользователь = владелец нового workspace."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..extensions import db
from ..models import User, Workspace
from ..security import check_csrf

bp = Blueprint("auth", __name__)


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)


@bp.get("/register")
def register():
    if current_user():
        return redirect(url_for("projects.index"))
    return render_template("auth/register.html")


@bp.post("/register")
def register_post():
    check_csrf()
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    password = request.form.get("password") or ""
    workspace_name = (request.form.get("workspace") or "").strip() or f"{name} workspace"

    if not email or not name or len(password) < 6:
        flash("Заполните имя, email и пароль (от 6 символов).", "error")
        return redirect(url_for("auth.register"))

    if User.query.filter_by(email=email).first():
        flash("Пользователь с таким email уже существует.", "error")
        return redirect(url_for("auth.register"))

    ws = Workspace(name=workspace_name)
    db.session.add(ws)
    db.session.flush()

    user = User(workspace_id=ws.id, email=email, name=name, role="owner")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session["user_id"] = user.id
    flash("Добро пожаловать в ClientDesk!", "success")
    return redirect(url_for("projects.index"))


@bp.get("/login")
def login():
    if current_user():
        return redirect(url_for("projects.index"))
    return render_template("auth/login.html")


@bp.post("/login")
def login_post():
    check_csrf()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        flash("Неверный email или пароль.", "error")
        return redirect(url_for("auth.login"))

    session["user_id"] = user.id
    nxt = request.args.get("next")
    return redirect(nxt or url_for("projects.index"))


@bp.post("/logout")
def logout():
    check_csrf()
    session.pop("user_id", None)
    flash("Вы вышли из аккаунта.", "success")
    return redirect(url_for("auth.login"))
