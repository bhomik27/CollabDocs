from django.db.models import Q
from rest_framework.exceptions import ValidationError

from documents import integration
from documents.serializers import DocumentFilterSerializer


def filter_documents(queryset, query_params):
    """
    Apply list filters as SQL via ORM lookups. Raises ValidationError (400)
    with per-parameter messages for malformed values. The queryset passed in
    must already be restricted to the caller's workspaces.
    """
    params = DocumentFilterSerializer(data=query_params)
    if not params.is_valid():
        raise ValidationError(params.errors)
    p = params.validated_data

    if "workspace" in p:
        queryset = queryset.filter(workspace_id=p["workspace"])
    if "status" in p:
        queryset = queryset.filter(status=p["status"])
    if "status_in" in p:
        queryset = queryset.filter(status__in=p["status_in"])
    if "created_by" in p:
        queryset = queryset.filter(created_by_id=p["created_by"])
    if "updated_after" in p:
        queryset = queryset.filter(updated_at__gte=p["updated_after"])
    if "updated_before" in p:
        queryset = queryset.filter(updated_at__lte=p["updated_before"])
    if p.get("search"):
        term = p["search"]
        queryset = queryset.filter(Q(title__icontains=term) | Q(content__icontains=term))
    if p.get("tag") and integration.DOCUMENT_TAGS_RELATION:
        # Joining the many-to-many can repeat a document; distinct() removes repeats.
        queryset = queryset.filter(**{f"{integration.DOCUMENT_TAGS_RELATION}__name": p["tag"]}).distinct()
    return queryset
