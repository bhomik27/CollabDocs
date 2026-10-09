"""
Audit endpoints (2 of Person C's 14). Read-only, workspace admins only (owners hold an admin membership).

  GET /api/workspaces/{workspace_id}/audit-logs/   WorkspaceAuditLogListView   (#13)
  GET /api/audit-logs/{id}/                        AuditLogDetailView          (#14)

List filters (query string): action, target_type, target_id, actor (user id),
created_after, created_before (ISO date or datetime).
Example: /api/workspaces/<workspace uuid>/audit-logs/?action=delete&target_type=comment&created_after=2026-10-01
"""
from datetime import datetime, time, timedelta, timezone

from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import generics
from rest_framework.exceptions import ValidationError

from core.access import admin_workspace_ids, get_workspace_for_user, require_role
from core.utils import parse_query_value

from .models import AuditLog
from .serializers import AuditLogSerializer


def _parse_when(name, raw):
    """Parse a date or datetime query parameter into (value, is_date); 400 naming the parameter if invalid.

    A bare date is returned as a timezone-aware UTC midnight datetime; the caller decides whether
    it means "from the start of that day" (created_after) or "through the end of it" (created_before).
    """
    value = parse_datetime(raw)
    if value is not None:
        return value, False
    day = parse_date(raw)
    if day is None:
        raise ValidationError({name: "Use an ISO date (2026-10-01) or datetime (2026-10-01T09:30:00Z)."})
    return datetime.combine(day, time.min, tzinfo=timezone.utc), True


class WorkspaceAuditLogListView(generics.ListAPIView):
    """Newest-first, paginated, filterable audit entries for one workspace."""

    serializer_class = AuditLogSerializer

    def get_queryset(self):
        workspace = get_workspace_for_user(self.request.user, self.kwargs["workspace_id"])  # non-member -> 404
        require_role(self.request.user, workspace.pk, "admin")                              # member but not admin -> 403
        qs = AuditLog.objects.filter(workspace_id=workspace.pk).select_related("actor")
        params = self.request.query_params
        for name in ("action", "target_type", "target_id"):
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        if params.get("actor"):  # a user id (UUID); malformed -> 400, not a 500 at query time
            qs = qs.filter(actor_id=parse_query_value(get_user_model(), "pk", "actor", params["actor"]))
        if params.get("created_after"):
            value, is_date = _parse_when("created_after", params["created_after"])
            qs = qs.filter(created_at__gte=value)
        if params.get("created_before"):
            value, is_date = _parse_when("created_before", params["created_before"])
            # a bare date means "through the end of that day" -> strictly before the next midnight
            qs = qs.filter(created_at__lt=value + timedelta(days=1)) if is_date else qs.filter(created_at__lte=value)
        return qs


class AuditLogDetailView(generics.RetrieveAPIView):
    """One audit entry. Scoped to workspaces where the user is admin/owner (otherwise 404)."""

    serializer_class = AuditLogSerializer

    def get_queryset(self):
        return AuditLog.objects.filter(workspace_id__in=admin_workspace_ids(self.request.user)).select_related("actor")
