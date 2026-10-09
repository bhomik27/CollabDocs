"""
THE INTEGRATION SEAM.

Every question Person C's code asks about Person A's world (workspaces, membership, roles)
or Person B's world (documents) is answered by a function in THIS file. No other file in
comments/, tags/ or audit/ imports Membership, Workspace or Document directly (except
models.py ForeignKeys and the audit registrations).

So on merge day, if A's role design differs from the stub, you edit this one file.

Assumptions (the "contract" - confirm with A and B):
  * workspaces.Workspace      - integer primary key
  * workspaces.Membership     - fields: workspace (FK), user (FK), role (str, one row per user per workspace)
  * role values               - "viewer" < "editor" < "admin" < "owner"
  * documents.Document        - integer primary key, field: workspace (FK)
"""
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from documents.models import Document
from workspaces.models import Membership, Workspace

# Higher number = more power. Used to answer "is this user AT LEAST an editor?".
ROLE_RANK = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}


def _roles_at_least(minimum):
    """Return the list of role names whose rank is >= `minimum`'s rank."""
    floor = ROLE_RANK[minimum]
    return [role for role, rank in ROLE_RANK.items() if rank >= floor]


def member_workspace_ids(user):
    """Subquery of workspace ids the user belongs to (any role).

    Used as `Model.objects.filter(workspace_id__in=member_workspace_ids(user))` so a user can
    never reach an object outside their workspaces (prevents IDOR; see BUILD_GUIDE step 4).
    """
    if not getattr(user, "is_authenticated", False):
        return Membership.objects.none().values("workspace_id")
    return Membership.objects.filter(user=user).values("workspace_id")


def admin_workspace_ids(user):
    """Subquery of workspace ids where the user is admin or owner."""
    if not getattr(user, "is_authenticated", False):
        return Membership.objects.none().values("workspace_id")
    return Membership.objects.filter(user=user, role__in=_roles_at_least("admin")).values("workspace_id")


def get_role(user, workspace_id):
    """Return the user's role name in the workspace, or None if not a member."""
    if not getattr(user, "is_authenticated", False):
        return None
    return Membership.objects.filter(user=user, workspace_id=workspace_id).values_list("role", flat=True).first()


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
    return get_object_or_404(Document.objects.filter(workspace_id__in=member_workspace_ids(user)), pk=document_id)
