"""JSON API точечных комментариев. Доступ: участник workspace ИЛИ клиент по magic-link токену.

Координаты пина хранятся в процентах (0..100), поэтому корректны на любом экране.
Realtime из спеки (Supabase channel) в локальном MVP заменён лёгким polling'ом на фронте.
"""
from datetime import datetime

from flask import Blueprint, abort, jsonify, request

from ..auth.routes import current_user
from ..extensions import db
from ..models import ClientLink, Comment, File
from ..security import check_csrf

bp = Blueprint("comments", __name__)


def resolve_access(file_id):
    """Возвращает (file, author_name, author_type, can_moderate) или abort(403/404).

    Клиент передаёт токен через заголовок X-Client-Token или поле `token` в JSON/query.
    """
    file = db.session.get(File, file_id)
    if not file:
        abort(404)

    user = current_user()
    if user and file.project.workspace_id == user.workspace_id:
        return file, user.name, "member", True

    token = (
        request.headers.get("X-Client-Token")
        or (request.get_json(silent=True) or {}).get("token")
        or request.args.get("token")
    )
    if token:
        link = ClientLink.query.filter_by(token=token, project_id=file.project_id).first()
        if link and link.is_valid:
            return file, "Клиент", "client", False

    abort(403)


def serialize(c):
    return {
        "id": c.id,
        "parent_id": c.parent_id,
        "author_name": c.author_name,
        "author_type": c.author_type,
        "body": c.body,
        "x": c.position_x,
        "y": c.position_y,
        "page": c.page,
        "resolved": c.resolved,
        "created_at": c.created_at.strftime("%d.%m.%Y %H:%M"),
        "replies": [serialize(r) for r in sorted(c.replies, key=lambda r: r.id)],
    }


@bp.get("/api/files/<int:file_id>/comments")
def list_comments(file_id):
    file, *_ = resolve_access(file_id)
    pins = (
        Comment.query.filter_by(file_id=file.id, parent_id=None)
        .order_by(Comment.created_at.asc())
        .all()
    )
    return jsonify([serialize(p) for p in pins])


@bp.post("/api/files/<int:file_id>/comments")
def create_comment(file_id):
    check_csrf()
    file, author_name, author_type, _ = resolve_access(file_id)
    data = request.get_json(silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "empty"}), 400

    parent_id = data.get("parent_id")
    x = y = None
    page = int(data.get("page") or 1)
    if parent_id:
        parent = db.session.get(Comment, parent_id)
        if not parent or parent.file_id != file.id:
            abort(404)
    else:
        # новый пин — координаты обязательны
        try:
            x = float(data.get("x"))
            y = float(data.get("y"))
        except (TypeError, ValueError):
            return jsonify({"error": "coords required"}), 400
        x = max(0.0, min(100.0, x))
        y = max(0.0, min(100.0, y))

    comment = Comment(
        project_id=file.project_id,
        file_id=file.id,
        parent_id=parent_id,
        author_name=author_name,
        author_type=author_type,
        body=body,
        position_x=x,
        position_y=y,
        page=page,
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify(serialize(comment if not parent_id else db.session.get(Comment, parent_id)))


@bp.post("/api/comments/<int:comment_id>/resolve")
def toggle_resolve(comment_id):
    check_csrf()
    comment = db.session.get(Comment, comment_id)
    if not comment:
        abort(404)
    file, _, _, can_moderate = resolve_access(comment.file_id)
    if not can_moderate:
        abort(403)
    comment.resolved = not comment.resolved
    db.session.commit()
    return jsonify({"ok": True, "resolved": comment.resolved})
