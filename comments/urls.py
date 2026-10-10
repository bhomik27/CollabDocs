from django.urls import path

from . import views

urlpatterns = [
    path("documents/<uuid:document_id>/comments/", views.DocumentCommentListCreateView.as_view(), name="document-comments"),
    path("comments/<int:pk>/", views.CommentDetailView.as_view(), name="comment-detail"),
]
