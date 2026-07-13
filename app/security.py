"""Общие декораторы и проверки: логин, CSRF, доступ к workspace."""
from functools import wraps

from flask import abort, flash, redirect, request, session, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Войдите, чтобы продолжить.", "error")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def check_csrf():
    """Вызывается в POST-роутах. Сравнивает токен формы с сессионным."""
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not sent or sent != session.get("csrf_token"):
        abort(400, "Bad CSRF token")
