"""Permission rules for tag endpoints."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.access import has_role


class TagPermission(BasePermission):
    """Any member may READ a tag; changing or deleting it needs the editor role or higher.

    (Membership itself is already enforced by the view's queryset: non-members get 404.)
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return has_role(request.user, obj.workspace_id, "editor")
