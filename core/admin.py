from django.contrib import admin

from .models import ClientLink, Comment, File, Profile, Project, StatusReport, Task, Workspace

for model in (Workspace, Profile, Project, File, Comment, Task, ClientLink, StatusReport):
    admin.site.register(model)
