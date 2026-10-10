from django.contrib import admin

from compat.models import AuditLog, Comment, Tag, Workspace, WorkspaceMember

admin.site.register([Workspace, WorkspaceMember, Tag, Comment, AuditLog])
