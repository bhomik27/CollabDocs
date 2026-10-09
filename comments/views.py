"""
Comment endpoints (5 of Person C's 14).

  GET/POST          /api/documents/{document_id}/comments/  DocumentCommentListCreateView (#1, #2)
  GET/PATCH/DELETE  /api/comments/{id}/                     CommentDetailView             (#3, #4, #5)
"""
from django.db import transaction
from django.db.models import Prefetch
from rest_framework import generics, status
from rest_framework.response import Response

from core.access import get_document_for_user, member_workspace_ids

from .models import Comment
from .permissions import CommentPermission
from .serializers import CommentEditSerializer, CommentSerializer, CommentWriteSerializer


class DocumentCommentListCreateView(generics.ListCreateAPIView):
    """List a document's top-level comments with replies nested (#1); add a comment/reply (#2)."""

    serializer_class = CommentSerializer

    def get_document(self):
        """Document from the URL, or 404 if the user is not in its workspace. Cached per request."""
        if not hasattr(self, "_document"):
            self._document = get_document_for_user(self.request.user, self.kwargs["document_id"])
        return self._document

    def get_queryset(self):
        # N+1 prevention: select_related pulls each author in the same JOIN; the Prefetch loads
        # ALL replies (with their authors) in one extra query instead of one query per comment.
        replies = Comment.objects.select_related("author")
        return (
            Comment.objects.filter(document=self.get_document(), parent__isnull=True)
            .select_related("author")
            .prefetch_related(Prefetch("replies", queryset=replies))
        )

    def create(self, request, *args, **kwargs):
        document = self.get_document()  # 404 for non-members happens here
        serializer = CommentWriteSerializer(data=request.data, context={"document": document, "request": request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():  # comment row + audit row (signal) commit together or not at all
            comment = serializer.save(author=request.user, document=document)  # author comes from auth, never from the client
        return Response(CommentSerializer(comment, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)


class CommentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Read (#3), edit own (#4) or delete (#5) one comment. Rules live in CommentPermission."""

    serializer_class = CommentSerializer
    permission_classes = generics.RetrieveUpdateDestroyAPIView.permission_classes + [CommentPermission]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        # Scoping: comments on documents outside the user's workspaces simply do not exist (404).
        return Comment.objects.filter(document__workspace_id__in=member_workspace_ids(self.request.user)).select_related(
            "author", "document"
        )

    def update(self, request, *args, **kwargs):
        comment = self.get_object()  # runs CommentPermission (author only for PATCH)
        serializer = CommentEditSerializer(comment, data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
        return Response(CommentSerializer(comment, context=self.get_serializer_context()).data)

    def perform_destroy(self, instance):
        # Hard delete. Replies cascade; each deleted comment gets its own audit entry.
        with transaction.atomic():
            instance.delete()
