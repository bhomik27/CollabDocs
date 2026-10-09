"""
Tag endpoints (7 of Person C's 14).

  GET/POST    /api/workspaces/{workspace_id}/tags/        WorkspaceTagListCreateView   (#6, #7)
  GET/PATCH/DELETE /api/tags/{id}/                        TagDetailView                (#8, #9, #10)
  POST        /api/documents/{document_id}/tags/          DocumentTagAttachView        (#11)
  DELETE      /api/documents/{document_id}/tags/{tag_id}/ DocumentTagDetachView        (#12)

Write operations run inside transaction.atomic() so the change and its audit-log row
(written by a signal) succeed or fail together.
"""
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access import (
    get_document_for_user,
    get_workspace_for_user,
    member_workspace_ids,
    require_role,
)

from .models import DocumentTag, Tag
from .permissions import TagPermission
from .serializers import AttachTagSerializer, DocumentTagSerializer, TagSerializer


class WorkspaceTagListCreateView(generics.ListCreateAPIView):
    """List a workspace's tags (any member) or create one (editor+)."""

    serializer_class = TagSerializer

    def get_workspace(self):
        """Workspace from the URL, or 404 if the user is not a member. Cached per request."""
        if not hasattr(self, "_workspace"):
            self._workspace = get_workspace_for_user(self.request.user, self.kwargs["workspace_id"])
        return self._workspace

    def get_queryset(self):
        # annotate(Count) computes each tag's document_count in the SAME query (avoids N+1).
        return (
            Tag.objects.filter(workspace_id=self.get_workspace().pk)
            .annotate(document_count=Count("document_tags"))
            .order_by("name")
        )

    def create(self, request, *args, **kwargs):
        workspace = self.get_workspace()
        require_role(request.user, workspace.pk, "editor")
        serializer = self.get_serializer(data=request.data, context={**self.get_serializer_context(), "workspace": workspace})
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                tag = serializer.save(workspace=workspace)
        except IntegrityError:  # two simultaneous requests passed validate_name; DB constraint caught the loser
            raise ValidationError({"name": "A tag with this name already exists in this workspace."})
        return Response(TagSerializer(tag).data, status=status.HTTP_201_CREATED)


class TagDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Read (member), rename/recolour (editor+) or delete (editor+) one tag."""

    serializer_class = TagSerializer
    permission_classes = generics.RetrieveUpdateDestroyAPIView.permission_classes + [TagPermission]
    http_method_names = ["get", "patch", "delete", "head", "options"]  # no PUT: PATCH covers editing

    def get_queryset(self):
        # Scoping: only tags in workspaces the user belongs to exist as far as this user knows.
        return Tag.objects.filter(workspace_id__in=member_workspace_ids(self.request.user)).annotate(
            document_count=Count("document_tags")
        )

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.save()

    def perform_destroy(self, instance):
        # Deleting a tag cascades to its DocumentTag rows; each one gets its own audit entry.
        with transaction.atomic():
            instance.delete()


class DocumentTagAttachView(APIView):
    """POST {"tag_id": N}: attach a tag to a document (editor+). Idempotent."""

    def post(self, request, document_id):
        document = get_document_for_user(request.user, document_id)
        require_role(request.user, document.workspace_id, "editor")
        serializer = AttachTagSerializer(data=request.data, context={"document": document})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # get_or_create makes repeating the call harmless: 201 the first time, 200 after.
            link, created = DocumentTag.objects.get_or_create(document=document, tag=serializer.validated_data["tag"])
        return Response(DocumentTagSerializer(link).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class DocumentTagDetachView(APIView):
    """DELETE: remove a tag from a document (editor+). 404 if it was not attached."""

    def delete(self, request, document_id, tag_id):
        document = get_document_for_user(request.user, document_id)
        require_role(request.user, document.workspace_id, "editor")
        link = get_object_or_404(DocumentTag, document=document, tag_id=tag_id)
        with transaction.atomic():
            link.delete()  # instance.delete() (not queryset.delete()) so the audit signal fires per object
        return Response(status=status.HTTP_204_NO_CONTENT)
