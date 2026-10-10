"""Role-based permissions shared by every app (Person B and C import these)."""
from rest_framework.permissions import BasePermission

from workspaces.models import WorkspaceMember


def get_workspace(obj):
    """Return the Workspace for a Workspace object or any object with .workspace."""
    return getattr(obj, "workspace", obj)


def get_role(user, workspace):
    """Return the user's role in the workspace, or None if not a member."""
    return (
        WorkspaceMember.objects.filter(workspace=workspace, user=user)
        .values_list("role", flat=True)
        .first()
    )


class IsWorkspaceMember(BasePermission):
    """Any member (admin, editor, viewer)."""
    message = "You are not a member of this workspace."

    def has_object_permission(self, request, view, obj):
        return get_role(request.user, get_workspace(obj)) is not None


class IsWorkspaceEditorOrAdmin(BasePermission):
    """Editors and admins only."""
    message = "Editor or admin role required."

    def has_object_permission(self, request, view, obj):
        return get_role(request.user, get_workspace(obj)) in (
            WorkspaceMember.Role.ADMIN,
            WorkspaceMember.Role.EDITOR,
        )


class IsWorkspaceAdmin(BasePermission):
    """Admins only."""
    message = "Admin role required for this action."

    def has_object_permission(self, request, view, obj):
        return get_role(request.user, get_workspace(obj)) == WorkspaceMember.Role.ADMIN
