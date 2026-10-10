"""Permission rules for the single-comment endpoint."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.access import has_role


class CommentPermission(BasePermission):
    """READ: any member (membership is enforced by the queryset -> non-members get 404).
    EDIT (PATCH): the author only - even admins cannot put words in someone's mouth.
    DELETE: the author, or an admin/owner of the workspace (moderation).
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if request.method == "PATCH":
            return obj.author_id == request.user.id
        if request.method == "DELETE":
            return obj.author_id == request.user.id or has_role(request.user, obj.document.workspace_id, "admin")
        return False
