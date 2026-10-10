import uuid

from django.db.models import Count, Max, Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents import integration, services
from documents.filters import filter_documents
from documents.models import Document, DocumentVersion
from documents.permissions import DocumentWorkspaceRolePermission
from documents.serializers import (
    DocumentListSerializer,
    DocumentSerializer,
    DocumentStatsSerializer,
    DocumentVersionListSerializer,
    DocumentVersionSerializer,
    RestoreResultSerializer,
)

VERSION_ID = r"(?P<version_id>[^/.]+)"


def _parse_uuid(value, message):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise NotFound(message)


class DocumentViewSet(viewsets.ModelViewSet):
    """
    CRUD for documents plus version history, restore and statistics.

    Querysets are tailored per action (see ``get_queryset``) so each endpoint
    runs a fixed number of queries regardless of how many rows it returns.
    """

    permission_classes = [IsAuthenticated, DocumentWorkspaceRolePermission]
    serializer_class = DocumentSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return DocumentListSerializer
        return DocumentSerializer

    def _tags_prefetch(self):
        if not integration.DOCUMENT_TAGS_RELATION:
            return []
        tag_model = Document._meta.get_field(integration.DOCUMENT_TAGS_RELATION).related_model
        return [Prefetch(integration.DOCUMENT_TAGS_RELATION, queryset=tag_model.objects.only("pk", "name").order_by("name"))]

    def get_queryset(self):
        queryset = Document.objects.for_user(self.request.user)

        if self.action == "list":
            queryset = filter_documents(queryset, self.request.query_params)
            return (
                queryset.select_related("workspace", "created_by")
                .prefetch_related(*self._tags_prefetch())
                .defer("content")
                # distinct=True keeps the count right if the tag filter joined extra rows.
                .annotate(version_count=Count("versions", distinct=True))
                .order_by("-updated_at", "id")
            )
        if self.action == "retrieve":
            return (
                queryset.select_related("workspace", "created_by")
                .prefetch_related(*self._tags_prefetch())
                .annotate(version_count=Count("versions"))
            )
        if self.action in {"update", "partial_update"}:
            return queryset.select_related("created_by")
        # versions / version_detail / restore / stats / destroy only need the
        # row for the permission check.
        return queryset.only("id", "workspace_id", "created_by_id")

    # ---- CRUD ---------------------------------------------------------------

    # create / update use the default ModelViewSet flow; DocumentSerializer.create()
    # and .update() delegate to documents.services, which wrap each write and its
    # version snapshot in transaction.atomic().

    def perform_destroy(self, instance):
        services.delete_document(instance)

    # ---- Versions -----------------------------------------------------------

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request, pk=None):
        document = self.get_object()
        versions = (
            DocumentVersion.objects.filter(document=document)
            .select_related("saved_by")
            .defer("content")
            .order_by("version_number")
        )
        return Response(DocumentVersionListSerializer(versions, many=True).data)

    @action(detail=True, methods=["get"], url_path=f"versions/{VERSION_ID}")
    def version_detail(self, request, pk=None, version_id=None):
        document = self.get_object()
        version_id = _parse_uuid(version_id, "Version not found.")
        try:
            version = DocumentVersion.objects.select_related("document", "saved_by", "restored_from").get(
                pk=version_id, document=document
            )
        except DocumentVersion.DoesNotExist:
            raise NotFound("Version not found for this document.")
        return Response(DocumentVersionSerializer(version).data)

    @action(detail=True, methods=["post"], url_path=f"versions/{VERSION_ID}/restore")
    def restore(self, request, pk=None, version_id=None):
        document = self.get_object()  # access + role check before taking any lock
        version_id = _parse_uuid(version_id, "Version not found.")
        document, version, source = services.restore_version(document.pk, version_id, user=request.user)
        result = RestoreResultSerializer(
            {"document": document, "version": version, "restored_from_version": source.version_number},
            context=self.get_serializer_context(),
        )
        return Response(result.data, status=status.HTTP_201_CREATED)

    # ---- Statistics ---------------------------------------------------------

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        document = self.get_object()
        versions = DocumentVersion.objects.filter(document=document)
        comments = integration.get_comment_model().objects.filter(document=document)

        # Separate aggregates per relation: joining versions and comments in
        # one query would multiply rows and inflate both counts.
        version_stats = versions.aggregate(
            version_count=Count("id"),
            latest_version_number=Max("version_number"),
            last_saved_at=Max("saved_at"),
        )
        comment_count = comments.aggregate(n=Count("id"))["n"]
        # UNION (not UNION ALL) de-duplicates users who both edited and commented.
        # order_by() clears default model ordering, which compound queries reject.
        contributor_ids = versions.exclude(saved_by=None).order_by().values_list("saved_by", flat=True).union(
            comments.exclude(**{integration.COMMENT_AUTHOR_FIELD: None}).order_by().values_list(
                integration.COMMENT_AUTHOR_FIELD, flat=True
            )
        )
        data = {
            "document_id": document.pk,
            **version_stats,
            "comment_count": comment_count,
            "contributor_count": contributor_ids.count(),
        }
        return Response(DocumentStatsSerializer(data).data)
