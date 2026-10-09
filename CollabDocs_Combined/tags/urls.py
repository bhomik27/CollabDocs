from django.urls import path

from . import views

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/tags/", views.WorkspaceTagListCreateView.as_view(), name="workspace-tags"),
    path("tags/<int:pk>/", views.TagDetailView.as_view(), name="tag-detail"),
    path("documents/<uuid:document_id>/tags/", views.DocumentTagAttachView.as_view(), name="document-tag-attach"),
    path("documents/<uuid:document_id>/tags/<int:tag_id>/", views.DocumentTagDetachView.as_view(), name="document-tag-detach"),
]
