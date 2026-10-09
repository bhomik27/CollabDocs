"""
THE INTEGRATION SEAM.

Every question Person C's code asks about Person A's world (workspaces, membership, roles)
or Person B's world (documents) is answered by a function in THIS file. No other file in
comments/, tags/ or audit/ imports WorkspaceMember, Workspace or Document directly (except
models.py ForeignKeys and the audit registrations).

Contract (as integrated):
  * workspaces.Workspace        - UUID primary key, `owner` FK
  * workspaces.WorkspaceMember  - fields: workspace (FK), user (FK), role (one row per user per workspace)
  * role values                 - "viewer" < "editor" < "admin"
  * documents.Document          - UUID primary key, field: workspace (FK)

Ownership: Person A stores the owner on Workspace.owner and gives the creator an "admin"
membership in the same transaction, so the membership row is the single source of truth
for authorization and an owner is treated exactly like an admin.
"""
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from workspaces.models import Workspace, WorkspaceMember

# Higher number = more power. Used to answer "is this user AT LEAST an editor?".
ROLE_RANK = {
    WorkspaceMember.Role.VIEWER: 1,
    WorkspaceMember.Role.EDITOR: 2,
    WorkspaceMember.Role.ADMIN: 3,
}


def _roles_at_least(minimum):
    """Return the list of role names whose rank is >= `minimum`'s rank."""
    floor = ROLE_RANK[minimum]
    return [role for role, rank in ROLE_RANK.items() if rank >= floor]


def member_workspace_ids(user):
    """Subquery of workspace ids the user belongs to (any role).

    Used as `Model.objects.filter(workspace_id__in=member_workspace_ids(user))` so a user can
    never reach an object outside their workspaces (prevents IDOR).
    """
    if not getattr(user, "is_authenticated", False):
        return WorkspaceMember.objects.none().values("workspace_id")
    return WorkspaceMember.objects.filter(user=user).values("workspace_id")


def admin_workspace_ids(user):
    """Subquery of workspace ids where the user is an admin (owners hold an admin membership)."""
    if not getattr(user, "is_authenticated", False):
        return WorkspaceMember.objects.none().values("workspace_id")
    return WorkspaceMember.objects.filter(user=user, role__in=_roles_at_least("admin")).values("workspace_id")


def get_role(user, workspace_id):
    """Return the user's role name in the workspace, or None if not a member."""
    if not getattr(user, "is_authenticated", False):
        return None
    return WorkspaceMember.objects.filter(user=user, workspace_id=workspace_id).values_list("role", flat=True).first()


def has_role(user, workspace_id, minimum):
    """True if the user's role in the workspace is `minimum` or higher."""
    role = get_role(user, workspace_id)
    return role is not None and ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]


def require_role(user, workspace_id, minimum):
    """Raise DRF-compatible PermissionDenied (HTTP 403) unless the user has at least `minimum`."""
    if not has_role(user, workspace_id, minimum):
        raise PermissionDenied(f"This action requires the '{minimum}' role or higher.")


def get_workspace_for_user(user, workspace_id):
    """Fetch a workspace the user belongs to, or raise Http404 (404, not 403: don't reveal existence)."""
    return get_object_or_404(Workspace.objects.filter(pk__in=member_workspace_ids(user)), pk=workspace_id)


def get_document_for_user(user, document_id):
    """Fetch a document in one of the user's workspaces, or raise Http404."""
    # Imported here, not at module level: documents.integration may delegate to this module,
    # and a top-level import would form documents.models -> integration -> access -> documents.models.
    from documents.models import Document

    return get_object_or_404(Document.objects.filter(workspace_id__in=member_workspace_ids(user)), pk=document_id)
