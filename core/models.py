"""Слой данных ClientDesk. Аутентификация — на встроенном django.contrib.auth.User;
принадлежность к workspace хранится в Profile. Изоляция арендаторов — на уровне запросов."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    """Связь пользователя с workspace + роль (owner/member)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=20, default="owner")

    def __str__(self):
        return f"{self.user.username} @ {self.workspace.name}"


class Project(models.Model):
    STATUS = [("active", "В работе"), ("on_hold", "На паузе"), ("done", "Завершён")]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=160)
    client_name = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS, default="active")
    deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class File(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="files")
    filename = models.CharField(max_length=255)     # исходное имя
    stored_name = models.CharField(max_length=255)  # имя на диске
    mime = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_image(self):
        return self.mime.startswith("image/")

    @property
    def is_pdf(self):
        return self.mime == "application/pdf"


class Comment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="comments")
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name="comments", null=True)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, related_name="replies", null=True, blank=True)
    author_name = models.CharField(max_length=120)
    author_type = models.CharField(max_length=20, default="member")  # member | client
    body = models.TextField()
    # координаты пина в процентах (0..100) — корректны на любом экране
    position_x = models.FloatField(null=True, blank=True)
    position_y = models.FloatField(null=True, blank=True)
    page = models.IntegerField(default=1)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Task(models.Model):
    STATUS = ["todo", "in_progress", "review", "done"]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, default="todo")
    assignee = models.CharField(max_length=120, blank=True, default="")
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]


class ClientLink(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="links")
    token = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=120, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def issue(cls, project, label=""):
        return cls.objects.create(
            project=project,
            token=secrets.token_urlsafe(24),
            label=label,
            expires_at=timezone.now() + timedelta(days=settings.CLIENT_LINK_TTL_DAYS),
        )

    @property
    def is_valid(self):
        return self.expires_at is None or self.expires_at > timezone.now()


class StatusReport(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="reports")
    period = models.CharField(max_length=60, blank=True, default="")
    content = models.TextField(blank=True, default="")
    generated_by = models.CharField(max_length=20, default="ai")  # ai | fallback
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
