"""Клиентский view по magic-link: только чтение проекта + возможность комментировать.
Регистрация не требуется — доступ по одноразовому непубличному токену с TTL."""
from flask import Blueprint, abort, render_template

from ..extensions import db
from ..models import ClientLink, File

bp = Blueprint("client", __name__)


def link_or_404(token):
    link = ClientLink.query.filter_by(token=token).first()
    if not link or not link.is_valid:
        abort(404)
    return link


@bp.get("/c/<token>")
def portal(token):
    link = link_or_404(token)
    project = link.project
    latest_report = (
        sorted(project.reports, key=lambda r: r.created_at, reverse=True)
        if project.reports
        else []
    )
    sent_reports = [r for r in latest_report if r.sent_at]
    return render_template(
        "client/portal.html",
        link=link,
        project=project,
        token=token,
        sent_reports=sent_reports,
        hide_nav=True,
    )


@bp.get("/c/<token>/files/<int:file_id>")
def file_view(token, file_id):
    link = link_or_404(token)
    file = db.session.get(File, file_id)
    if not file or file.project_id != link.project_id:
        abort(404)
    return render_template(
        "projects/file_view.html",
        project=link.project,
        file=file,
        is_client=True,
        token=token,
        hide_nav=True,
    )
