"""CRUD проектов, загрузка/выдача файлов, задачи Kanban, клиентские ссылки."""
import mimetypes
import secrets
from datetime import date, datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from ..auth.routes import current_user
from ..extensions import db
from ..models import ClientLink, Comment, File, Project, StatusReport, Task
from ..security import check_csrf, login_required

bp = Blueprint("projects", __name__)

TASK_STATUSES = ["todo", "in_progress", "review", "done"]


# --------------------------- helpers ---------------------------

def owned_project_or_404(project_id):
    """Проект строго внутри workspace текущего пользователя (изоляция арендаторов)."""
    user = current_user()
    project = db.session.get(Project, project_id)
    if not project or project.workspace_id != user.workspace_id:
        abort(404)
    return project


def _allowed(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


# --------------------------- проекты ---------------------------

@bp.get("/")
@login_required
def index():
    user = current_user()
    projects = (
        Project.query.filter_by(workspace_id=user.workspace_id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return render_template("projects/index.html", projects=projects)


@bp.post("/projects")
@login_required
def create():
    check_csrf()
    user = current_user()
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Укажите название проекта.", "error")
        return redirect(url_for("projects.index"))

    deadline = None
    raw_deadline = request.form.get("deadline")
    if raw_deadline:
        try:
            deadline = datetime.strptime(raw_deadline, "%Y-%m-%d").date()
        except ValueError:
            deadline = None

    project = Project(
        workspace_id=user.workspace_id,
        name=name,
        client_name=(request.form.get("client_name") or "").strip(),
        deadline=deadline,
    )
    db.session.add(project)
    db.session.commit()
    flash("Проект создан.", "success")
    return redirect(url_for("projects.detail", project_id=project.id))


@bp.get("/projects/<int:project_id>")
@login_required
def detail(project_id):
    project = owned_project_or_404(project_id)
    tasks_by_status = {s: [] for s in TASK_STATUSES}
    for t in sorted(project.tasks, key=lambda x: (x.position, x.id)):
        tasks_by_status.setdefault(t.status, []).append(t)
    reports = sorted(project.reports, key=lambda r: r.created_at, reverse=True)
    return render_template(
        "projects/detail.html",
        project=project,
        tasks_by_status=tasks_by_status,
        statuses=TASK_STATUSES,
        reports=reports,
    )


@bp.post("/projects/<int:project_id>/status")
@login_required
def update_status(project_id):
    check_csrf()
    project = owned_project_or_404(project_id)
    status = request.form.get("status")
    if status in {"active", "on_hold", "done"}:
        project.status = status
        db.session.commit()
    return redirect(url_for("projects.detail", project_id=project.id))


@bp.post("/projects/<int:project_id>/delete")
@login_required
def delete(project_id):
    check_csrf()
    project = owned_project_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash("Проект удалён.", "success")
    return redirect(url_for("projects.index"))


# --------------------------- файлы ---------------------------

@bp.post("/projects/<int:project_id>/files")
@login_required
def upload_file(project_id):
    check_csrf()
    project = owned_project_or_404(project_id)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Файл не выбран.", "error")
        return redirect(url_for("projects.detail", project_id=project.id))
    if not _allowed(f.filename):
        flash("Недопустимый тип файла.", "error")
        return redirect(url_for("projects.detail", project_id=project.id))

    original = secure_filename(f.filename)
    ext = original.rsplit(".", 1)[-1].lower()
    stored = f"{secrets.token_hex(16)}.{ext}"
    f.save(current_app.config["UPLOAD_DIR"] / stored)
    mime = f.mimetype or mimetypes.guess_type(original)[0] or "application/octet-stream"

    record = File(project_id=project.id, filename=original, stored_name=stored, mime=mime)
    db.session.add(record)
    db.session.commit()
    flash("Файл загружен.", "success")
    return redirect(url_for("projects.file_view", project_id=project.id, file_id=record.id))


@bp.get("/uploads/<path:stored_name>")
def raw_file(stored_name):
    # Файлы отдаются по непредсказуемому stored_name (24 байта энтропии).
    return send_from_directory(current_app.config["UPLOAD_DIR"], stored_name)


@bp.get("/projects/<int:project_id>/files/<int:file_id>")
@login_required
def file_view(project_id, file_id):
    project = owned_project_or_404(project_id)
    file = db.session.get(File, file_id)
    if not file or file.project_id != project.id:
        abort(404)
    return render_template(
        "projects/file_view.html", project=project, file=file, is_client=False
    )


@bp.post("/projects/<int:project_id>/files/<int:file_id>/delete")
@login_required
def delete_file(project_id, file_id):
    check_csrf()
    project = owned_project_or_404(project_id)
    file = db.session.get(File, file_id)
    if not file or file.project_id != project.id:
        abort(404)
    try:
        (current_app.config["UPLOAD_DIR"] / file.stored_name).unlink(missing_ok=True)
    except OSError:
        pass
    db.session.delete(file)
    db.session.commit()
    return redirect(url_for("projects.detail", project_id=project.id))


# --------------------------- задачи (Kanban) ---------------------------

@bp.post("/projects/<int:project_id>/tasks")
@login_required
def create_task(project_id):
    check_csrf()
    project = owned_project_or_404(project_id)
    title = (request.form.get("title") or "").strip()
    if not title:
        return redirect(url_for("projects.detail", project_id=project.id))
    task = Task(
        project_id=project.id,
        title=title,
        description=(request.form.get("description") or "").strip(),
        assignee=(request.form.get("assignee") or "").strip(),
        status="todo",
    )
    db.session.add(task)
    db.session.commit()
    return redirect(url_for("projects.detail", project_id=project.id))


@bp.post("/api/tasks/<int:task_id>/move")
@login_required
def move_task(task_id):
    """Drag-and-drop: смена статуса/порядка. JSON от Alpine."""
    check_csrf()
    task = db.session.get(Task, task_id)
    if not task or task.project.workspace_id != current_user().workspace_id:
        abort(404)
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status in TASK_STATUSES:
        if status == "done" and task.status != "done":
            task.done_at = datetime.utcnow()
        if status != "done":
            task.done_at = None
        task.status = status
    if isinstance(data.get("position"), int):
        task.position = data["position"]
    db.session.commit()
    return jsonify({"ok": True})


@bp.post("/api/tasks/<int:task_id>/delete")
@login_required
def delete_task(task_id):
    check_csrf()
    task = db.session.get(Task, task_id)
    if not task or task.project.workspace_id != current_user().workspace_id:
        abort(404)
    pid = task.project_id
    db.session.delete(task)
    db.session.commit()
    return jsonify({"ok": True, "project_id": pid})


# --------------------------- клиентские magic-link'и ---------------------------

@bp.post("/projects/<int:project_id>/links")
@login_required
def create_link(project_id):
    check_csrf()
    project = owned_project_or_404(project_id)
    link = ClientLink.make(
        project.id,
        current_app.config["CLIENT_LINK_TTL_DAYS"],
        label=(request.form.get("label") or "").strip(),
    )
    db.session.add(link)
    db.session.commit()
    flash("Клиентская ссылка создана.", "success")
    return redirect(url_for("projects.detail", project_id=project.id))


@bp.post("/projects/<int:project_id>/links/<int:link_id>/revoke")
@login_required
def revoke_link(project_id, link_id):
    check_csrf()
    project = owned_project_or_404(project_id)
    link = db.session.get(ClientLink, link_id)
    if not link or link.project_id != project.id:
        abort(404)
    db.session.delete(link)
    db.session.commit()
    return redirect(url_for("projects.detail", project_id=project.id))
