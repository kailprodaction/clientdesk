"""Все представления ClientDesk. Изоляция арендаторов — через owned_project()."""
import json
import mimetypes
import secrets
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .ai import generate_status_report, summarize_feedback
from .models import ClientLink, Comment, File, Profile, Project, StatusReport, Task, Workspace

TASK_STATUSES = ["todo", "in_progress", "review", "done"]


# --------------------------- helpers ---------------------------

def _workspace(request):
    return request.user.profile.workspace


def owned_project(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if project.workspace_id != _workspace(request).id:
        raise Http404
    return project


def _allowed(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in settings.UPLOAD_ALLOWED


def _serialize(c):
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
        "created_at": timezone.localtime(c.created_at).strftime("%d.%m.%Y %H:%M"),
        "replies": [_serialize(r) for r in c.replies.order_by("id")],
    }


def resolve_access(request, file_id):
    """(file, author_name, author_type, can_moderate) — участник workspace ИЛИ клиент по токену."""
    file = get_object_or_404(File, pk=file_id)
    user = request.user
    if user.is_authenticated and file.project.workspace_id == user.profile.workspace_id:
        return file, (user.get_full_name() or user.username), "member", True

    token = (
        request.headers.get("X-Client-Token")
        or request.GET.get("token")
        or (json.loads(request.body or b"{}").get("token") if request.body else None)
    )
    if token:
        link = ClientLink.objects.filter(token=token, project_id=file.project_id).first()
        if link and link.is_valid:
            return file, "Клиент", "client", False
    raise Http404


# --------------------------- auth ---------------------------

def register(request):
    if request.user.is_authenticated:
        return redirect("index")
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        name = (request.POST.get("name") or "").strip()
        password = request.POST.get("password") or ""
        ws_name = (request.POST.get("workspace") or "").strip() or f"{name} workspace"
        if not email or not name or len(password) < 6:
            messages.error(request, "Заполните имя, email и пароль (от 6 символов).")
            return redirect("register")
        if User.objects.filter(username=email).exists():
            messages.error(request, "Пользователь с таким email уже существует.")
            return redirect("register")
        with transaction.atomic():
            ws = Workspace.objects.create(name=ws_name)
            user = User.objects.create_user(username=email, email=email, password=password, first_name=name)
            Profile.objects.create(user=user, workspace=ws, role="owner")
        login(request, user)
        messages.success(request, "Добро пожаловать в ClientDesk!")
        return redirect("index")
    return render(request, "auth/register.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("index")
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=email, password=password)
        if not user:
            messages.error(request, "Неверный email или пароль.")
            return redirect("login")
        login(request, user)
        return redirect(request.GET.get("next") or "index")
    return render(request, "auth/login.html")


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Вы вышли из аккаунта.")
    return redirect("login")


# --------------------------- projects ---------------------------

@login_required
def index(request):
    projects = Project.objects.filter(workspace=_workspace(request))
    return render(request, "projects/index.html", {"projects": projects})


@login_required
@require_POST
def project_create(request):
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "Укажите название проекта.")
        return redirect("index")
    deadline = None
    raw = request.POST.get("deadline")
    if raw:
        try:
            deadline = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            deadline = None
    project = Project.objects.create(
        workspace=_workspace(request),
        name=name,
        client_name=(request.POST.get("client_name") or "").strip(),
        deadline=deadline,
    )
    messages.success(request, "Проект создан.")
    return redirect("project_detail", project_id=project.id)


@login_required
@ensure_csrf_cookie
def project_detail(request, project_id):
    project = owned_project(request, project_id)
    tasks_by_status = {s: [] for s in TASK_STATUSES}
    for t in project.tasks.all():
        tasks_by_status.setdefault(t.status, []).append(t)
    return render(request, "projects/detail.html", {
        "project": project,
        "tasks_by_status": tasks_by_status,
        "statuses": TASK_STATUSES,
        "reports": project.reports.all(),
    })


@login_required
@require_POST
def project_status(request, project_id):
    project = owned_project(request, project_id)
    status = request.POST.get("status")
    if status in {"active", "on_hold", "done"}:
        project.status = status
        project.save(update_fields=["status"])
    return redirect("project_detail", project_id=project.id)


@login_required
@require_POST
def project_delete(request, project_id):
    project = owned_project(request, project_id)
    project.delete()
    messages.success(request, "Проект удалён.")
    return redirect("index")


# --------------------------- files ---------------------------

@login_required
@require_POST
def file_upload(request, project_id):
    project = owned_project(request, project_id)
    f = request.FILES.get("file")
    if not f:
        messages.error(request, "Файл не выбран.")
        return redirect("project_detail", project_id=project.id)
    if not _allowed(f.name):
        messages.error(request, "Недопустимый тип файла.")
        return redirect("project_detail", project_id=project.id)
    ext = f.name.rsplit(".", 1)[-1].lower()
    stored = f"{secrets.token_hex(16)}.{ext}"
    settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    with open(settings.MEDIA_ROOT / stored, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)
    mime = f.content_type or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    record = File.objects.create(project=project, filename=f.name, stored_name=stored, mime=mime)
    messages.success(request, "Файл загружен.")
    return redirect("file_view", project_id=project.id, file_id=record.id)


def raw_file(request, stored_name):
    path = settings.MEDIA_ROOT / stored_name
    if not path.exists():
        raise Http404
    return FileResponse(open(path, "rb"))


@login_required
@ensure_csrf_cookie
def file_view(request, project_id, file_id):
    project = owned_project(request, project_id)
    file = get_object_or_404(File, pk=file_id, project=project)
    return render(request, "projects/file_view.html", {
        "project": project, "file": file, "is_client": False,
    })


@login_required
@require_POST
def file_delete(request, project_id, file_id):
    project = owned_project(request, project_id)
    file = get_object_or_404(File, pk=file_id, project=project)
    (settings.MEDIA_ROOT / file.stored_name).unlink(missing_ok=True)
    file.delete()
    return redirect("project_detail", project_id=project.id)


# --------------------------- tasks (Kanban) ---------------------------

@login_required
@require_POST
def task_create(request, project_id):
    project = owned_project(request, project_id)
    title = (request.POST.get("title") or "").strip()
    if title:
        Task.objects.create(
            project=project, title=title,
            description=(request.POST.get("description") or "").strip(),
            assignee=(request.POST.get("assignee") or "").strip(),
        )
    return redirect("project_detail", project_id=project.id)


@login_required
@require_POST
def task_move(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    if task.project.workspace_id != _workspace(request).id:
        raise Http404
    data = json.loads(request.body or b"{}")
    status = data.get("status")
    if status in TASK_STATUSES:
        if status == "done" and task.status != "done":
            task.done_at = timezone.now()
        if status != "done":
            task.done_at = None
        task.status = status
    if isinstance(data.get("position"), int):
        task.position = data["position"]
    task.save()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def task_delete(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    if task.project.workspace_id != _workspace(request).id:
        raise Http404
    task.delete()
    return JsonResponse({"ok": True})


# --------------------------- client links ---------------------------

@login_required
@require_POST
def link_create(request, project_id):
    project = owned_project(request, project_id)
    ClientLink.issue(project, label=(request.POST.get("label") or "").strip())
    messages.success(request, "Клиентская ссылка создана.")
    return redirect("project_detail", project_id=project.id)


@login_required
@require_POST
def link_revoke(request, project_id, link_id):
    project = owned_project(request, project_id)
    get_object_or_404(ClientLink, pk=link_id, project=project).delete()
    return redirect("project_detail", project_id=project.id)


# --------------------------- comments API ---------------------------

def comments_list(request, file_id):
    file, *_ = resolve_access(request, file_id)
    pins = file.comments.filter(parent__isnull=True)
    return JsonResponse([_serialize(p) for p in pins], safe=False)


@require_POST
def comment_create(request, file_id):
    file, author_name, author_type, _ = resolve_access(request, file_id)
    data = json.loads(request.body or b"{}")
    body = (data.get("body") or "").strip()
    if not body:
        return JsonResponse({"error": "empty"}, status=400)

    parent_id = data.get("parent_id")
    x = y = None
    page = int(data.get("page") or 1)
    if parent_id:
        parent = get_object_or_404(Comment, pk=parent_id, file=file)
    else:
        try:
            x = max(0.0, min(100.0, float(data.get("x"))))
            y = max(0.0, min(100.0, float(data.get("y"))))
        except (TypeError, ValueError):
            return JsonResponse({"error": "coords required"}, status=400)

    comment = Comment.objects.create(
        project=file.project, file=file, parent_id=parent_id,
        author_name=author_name, author_type=author_type, body=body,
        position_x=x, position_y=y, page=page,
    )
    top = comment if not parent_id else get_object_or_404(Comment, pk=parent_id)
    return JsonResponse(_serialize(top), safe=False)


@require_POST
def comment_resolve(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    _, _, _, can_moderate = resolve_access(request, comment.file_id)
    if not can_moderate:
        raise Http404
    comment.resolved = not comment.resolved
    comment.save(update_fields=["resolved"])
    return JsonResponse({"ok": True, "resolved": comment.resolved})


# --------------------------- AI ---------------------------

@login_required
@require_POST
def report_generate(request, project_id):
    project = owned_project(request, project_id)
    content, source = generate_status_report(project)
    report = StatusReport.objects.create(
        project=project,
        period=timezone.now().strftime("Неделя до %d.%m.%Y"),
        content=content, generated_by=source,
    )
    messages.success(request, "Черновик отчёта готов." + ("" if source == "ai" else " (офлайн-режим без Claude API)"))
    return redirect(f"{request.build_absolute_uri(project_url(project))}#report-{report.id}")


def project_url(project):
    from django.urls import reverse
    return reverse("project_detail", args=[project.id])


@login_required
@require_POST
def report_update(request, report_id):
    report = get_object_or_404(StatusReport, pk=report_id)
    if report.project.workspace_id != _workspace(request).id:
        raise Http404
    report.content = request.POST.get("content", report.content)
    report.save(update_fields=["content"])
    messages.success(request, "Отчёт сохранён.")
    return redirect("project_detail", project_id=report.project_id)


@login_required
@require_POST
def report_send(request, report_id):
    report = get_object_or_404(StatusReport, pk=report_id)
    if report.project.workspace_id != _workspace(request).id:
        raise Http404
    report.sent_at = timezone.now()
    report.save(update_fields=["sent_at"])
    messages.success(request, "Отчёт отправлен клиенту (виден в клиентском портале).")
    return redirect("project_detail", project_id=report.project_id)


@login_required
@require_POST
def feedback_summary(request, project_id):
    project = owned_project(request, project_id)
    content, source = summarize_feedback(project)
    return JsonResponse({"content": content, "source": source})


# --------------------------- client portal ---------------------------

def _valid_link(token):
    link = ClientLink.objects.filter(token=token).first()
    if not link or not link.is_valid:
        raise Http404
    return link


@ensure_csrf_cookie
def client_portal(request, token):
    link = _valid_link(token)
    project = link.project
    sent_reports = project.reports.filter(sent_at__isnull=False)
    done = project.tasks.filter(status="done").count()
    return render(request, "client/portal.html", {
        "link": link, "project": project, "token": token,
        "sent_reports": sent_reports, "done_count": done,
        "task_total": project.tasks.count(), "hide_nav": True,
    })


@ensure_csrf_cookie
def client_file_view(request, token, file_id):
    link = _valid_link(token)
    file = get_object_or_404(File, pk=file_id, project=link.project)
    return render(request, "projects/file_view.html", {
        "project": link.project, "file": file, "is_client": True,
        "token": token, "hide_nav": True,
    })


def healthz(request):
    return JsonResponse({"status": "ok"})
