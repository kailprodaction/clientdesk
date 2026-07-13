"""Эндпоинты AI-фич: генерация статус-отчёта и summary фидбека.
В спеке — асинхронно через Cloud Tasks; локально выполняем синхронно."""
from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, redirect, request, url_for

from ..auth.routes import current_user
from ..extensions import db
from ..models import Project, StatusReport
from ..security import check_csrf, login_required
from .service import generate_status_report, summarize_feedback

bp = Blueprint("ai", __name__)


def _owned(project_id):
    project = db.session.get(Project, project_id)
    if not project or project.workspace_id != current_user().workspace_id:
        abort(404)
    return project


@bp.post("/projects/<int:project_id>/reports/generate")
@login_required
def generate_report(project_id):
    check_csrf()
    project = _owned(project_id)
    content, source = generate_status_report(project)
    report = StatusReport(
        project_id=project.id,
        period=datetime.utcnow().strftime("Неделя до %d.%m.%Y"),
        content=content,
        generated_by=source,
    )
    db.session.add(report)
    db.session.commit()
    flash(
        "Черновик отчёта готов." + ("" if source == "ai" else " (офлайн-режим без Claude API)"),
        "success",
    )
    return redirect(url_for("projects.detail", project_id=project.id) + f"#report-{report.id}")


@bp.post("/reports/<int:report_id>/update")
@login_required
def update_report(report_id):
    check_csrf()
    report = db.session.get(StatusReport, report_id)
    if not report or report.project.workspace_id != current_user().workspace_id:
        abort(404)
    report.content = request.form.get("content", report.content)
    db.session.commit()
    flash("Отчёт сохранён.", "success")
    return redirect(url_for("projects.detail", project_id=report.project_id) + f"#report-{report.id}")


@bp.post("/reports/<int:report_id>/send")
@login_required
def send_report(report_id):
    check_csrf()
    report = db.session.get(StatusReport, report_id)
    if not report or report.project.workspace_id != current_user().workspace_id:
        abort(404)
    # В спеке — Resend. Локально просто помечаем отправленным и показываем клиенту в портале.
    report.sent_at = datetime.utcnow()
    db.session.commit()
    flash("Отчёт отправлен клиенту (виден в клиентском портале).", "success")
    return redirect(url_for("projects.detail", project_id=report.project_id))


@bp.post("/projects/<int:project_id>/feedback/summarize")
@login_required
def feedback_summary(project_id):
    project = _owned(project_id)
    check_csrf()
    content, source = summarize_feedback(project)
    return jsonify({"content": content, "source": source})
