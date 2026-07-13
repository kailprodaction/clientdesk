from django.urls import path

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),

    # auth
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # projects
    path("", views.index, name="index"),
    path("projects/create", views.project_create, name="project_create"),
    path("projects/<int:project_id>/", views.project_detail, name="project_detail"),
    path("projects/<int:project_id>/status", views.project_status, name="project_status"),
    path("projects/<int:project_id>/delete", views.project_delete, name="project_delete"),

    # files
    path("projects/<int:project_id>/files", views.file_upload, name="file_upload"),
    path("projects/<int:project_id>/files/<int:file_id>/", views.file_view, name="file_view"),
    path("projects/<int:project_id>/files/<int:file_id>/delete", views.file_delete, name="file_delete"),
    path("uploads/<str:stored_name>", views.raw_file, name="raw_file"),

    # tasks
    path("projects/<int:project_id>/tasks", views.task_create, name="task_create"),
    path("api/tasks/<int:task_id>/move", views.task_move, name="task_move"),
    path("api/tasks/<int:task_id>/delete", views.task_delete, name="task_delete"),

    # client links
    path("projects/<int:project_id>/links", views.link_create, name="link_create"),
    path("projects/<int:project_id>/links/<int:link_id>/revoke", views.link_revoke, name="link_revoke"),

    # comments API
    path("api/files/<int:file_id>/comments", views.comments_list, name="comments_list"),
    path("api/files/<int:file_id>/comments/create", views.comment_create, name="comment_create"),
    path("api/comments/<int:comment_id>/resolve", views.comment_resolve, name="comment_resolve"),

    # AI
    path("projects/<int:project_id>/reports/generate", views.report_generate, name="report_generate"),
    path("reports/<int:report_id>/update", views.report_update, name="report_update"),
    path("reports/<int:report_id>/send", views.report_send, name="report_send"),
    path("projects/<int:project_id>/feedback/summarize", views.feedback_summary, name="feedback_summary"),

    # client portal
    path("c/<str:token>/", views.client_portal, name="client_portal"),
    path("c/<str:token>/files/<int:file_id>/", views.client_file_view, name="client_file_view"),
]
