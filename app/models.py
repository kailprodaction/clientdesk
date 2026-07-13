"""Слой данных. В спеке это Supabase/Postgres + RLS; локально — SQLite через SQLAlchemy.
Изоляция workspace обеспечивается на уровне запросов (см. helpers в блюпринтах)."""
import secrets
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def _now():
    return datetime.utcnow()


class Workspace(db.Model):
    __tablename__ = "workspaces"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=_now)

    members = db.relationship("User", back_populates="workspace", cascade="all, delete-orphan")
    projects = db.relationship("Project", back_populates="workspace", cascade="all, delete-orphan")


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="owner")  # owner | member
    created_at = db.Column(db.DateTime, default=_now)

    workspace = db.relationship("Workspace", back_populates="members")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    client_name = db.Column(db.String(160), nullable=False, default="")
    status = db.Column(db.String(20), default="active")  # active | on_hold | done
    deadline = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    workspace = db.relationship("Workspace", back_populates="projects")
    files = db.relationship("File", back_populates="project", cascade="all, delete-orphan")
    tasks = db.relationship("Task", back_populates="project", cascade="all, delete-orphan")
    comments = db.relationship("Comment", back_populates="project", cascade="all, delete-orphan")
    links = db.relationship("ClientLink", back_populates="project", cascade="all, delete-orphan")
    reports = db.relationship("StatusReport", back_populates="project", cascade="all, delete-orphan")


class File(db.Model):
    __tablename__ = "files"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # исходное имя
    stored_name = db.Column(db.String(255), nullable=False)  # имя на диске
    mime = db.Column(db.String(120), default="")
    created_at = db.Column(db.DateTime, default=_now)

    project = db.relationship("Project", back_populates="files")
    comments = db.relationship("Comment", back_populates="file", cascade="all, delete-orphan")

    @property
    def is_image(self):
        return self.mime.startswith("image/")

    @property
    def is_pdf(self):
        return self.mime == "application/pdf"


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id"), nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=True)
    author_name = db.Column(db.String(120), nullable=False)
    author_type = db.Column(db.String(20), default="member")  # member | client
    body = db.Column(db.Text, nullable=False)
    # Координаты точечного комментария в процентах (0..100) — не в px, работает на любом экране
    position_x = db.Column(db.Float, nullable=True)
    position_y = db.Column(db.Float, nullable=True)
    page = db.Column(db.Integer, default=1)  # для PDF
    resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_now)

    project = db.relationship("Project", back_populates="comments")
    file = db.relationship("File", back_populates="comments")
    replies = db.relationship(
        "Comment", backref=db.backref("parent", remote_side=[id]), cascade="all, delete-orphan"
    )

    @property
    def is_pin(self):
        return self.position_x is not None and self.parent_id is None


class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="todo")  # todo | in_progress | review | done
    assignee = db.Column(db.String(120), default="")
    position = db.Column(db.Integer, default=0)  # порядок внутри колонки
    created_at = db.Column(db.DateTime, default=_now)
    done_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship("Project", back_populates="tasks")


class ClientLink(db.Model):
    __tablename__ = "client_links"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(24))
    label = db.Column(db.String(120), default="")
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    project = db.relationship("Project", back_populates="links")

    @staticmethod
    def make(project_id, ttl_days, label=""):
        return ClientLink(
            project_id=project_id,
            label=label,
            expires_at=_now() + timedelta(days=ttl_days),
        )

    @property
    def is_valid(self):
        return self.expires_at is None or self.expires_at > _now()


class StatusReport(db.Model):
    __tablename__ = "status_reports"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    period = db.Column(db.String(60), default="")
    content = db.Column(db.Text, default="")
    generated_by = db.Column(db.String(20), default="ai")  # ai | fallback
    created_at = db.Column(db.DateTime, default=_now)
    sent_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship("Project", back_populates="reports")
