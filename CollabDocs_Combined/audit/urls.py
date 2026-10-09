from django.urls import path

from . import views

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/audit-logs/", views.WorkspaceAuditLogListView.as_view(), name="workspace-audit-logs"),
    path("audit-logs/<int:pk>/", views.AuditLogDetailView.as_view(), name="audit-log-detail"),
]
