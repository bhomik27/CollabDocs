"""
Workspace role policy for documents.

    action                         viewer  editor  admin
    list / retrieve / versions /     yes     yes    yes
      version detail / stats
    create                           no      yes    yes
    update (PUT/PATCH) / restore     no      yes    yes
    delete                           no      own*   yes

    * an editor may delete documents they created.

Non-members never see a workspace's documents: they are filtered out of the
queryset, so object endpoints answer 404 (resource concealment), while members
lacking the role get 403. Create is checked in DocumentSerializer because the
target workspace comes from the request body.

When Person A's permission classes are integrated, keep this class (it is
document-specific) but make ``documents.integration`` read their membership
model; or swap in their class if it implements the same table.
"""

from rest_framework.permissions import BasePermission

from documents import integration

READ_ACTIONS = {"list", "retrieve", "versions", "version_detail", "stats"}
WRITE_ACTIONS = {"create", "update", "partial_update", "restore"}


class DocumentWorkspaceRolePermission(BasePermission):
    message = "Your workspace role does not allow this action."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        role = getattr(obj, "user_role", None)
        if role is None:
            role = integration.get_role(request.user, obj.workspace_id)
        if role is None:
            return False

        action = view.action
        if action in READ_ACTIONS:
            return role in integration.READ_ROLES
        if action in WRITE_ACTIONS:
            return role in integration.WRITE_ROLES
        if action == "destroy":
            if role == integration.ROLE_ADMIN:
                return True
            if role == integration.ROLE_EDITOR and obj.created_by_id == request.user.pk:
                return True
            self.message = "Only workspace admins, or the editor who created it, can delete a document."
            return False
        return False
