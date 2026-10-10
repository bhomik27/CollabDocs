"""
Integration seam between the Documents app and teammates' apps.

Every reference the Documents app makes to a model it does not own goes
through this module, so final integration means changing settings (and one
migration) instead of hunting for imports.

Contract expected from the real models (field names must match):

    Workspace           primary key ``id`` (UUID)
    WorkspaceMember     ``workspace`` FK, ``user`` FK, ``role`` in {admin, editor, viewer}
    Comment             ``document`` FK to documents.Document (related_name="comments"),
                        ``author`` FK to the user model
    Tag                 M2M to documents.Document exposed as ``Document.tags``,
                        with a ``name`` field

The defaults below are the integrated apps (Person A's ``workspaces``, Person
C's ``comments`` and ``tags``); config/settings.py sets them explicitly.
``Document.tags`` is the reverse accessor of ``tags.Tag.documents`` (through
``tags.DocumentTag``).
"""

from django.apps import apps
from django.conf import settings

WORKSPACE_MODEL = getattr(settings, "COLLABDOCS_WORKSPACE_MODEL", "workspaces.Workspace")
WORKSPACE_MEMBER_MODEL = getattr(settings, "COLLABDOCS_WORKSPACE_MEMBER_MODEL", "workspaces.WorkspaceMember")
COMMENT_MODEL = getattr(settings, "COLLABDOCS_COMMENT_MODEL", "comments.Comment")
# Reverse accessor of the Tag <-> Document many-to-many. Set to None if the
# integrated project has no tags, which disables tag prefetching and filtering.
DOCUMENT_TAGS_RELATION = getattr(settings, "COLLABDOCS_DOCUMENT_TAGS_RELATION", "tags")
COMMENT_AUTHOR_FIELD = getattr(settings, "COLLABDOCS_COMMENT_AUTHOR_FIELD", "author")

ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

READ_ROLES = frozenset({ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER})
WRITE_ROLES = frozenset({ROLE_ADMIN, ROLE_EDITOR})


def get_workspace_model():
    return apps.get_model(WORKSPACE_MODEL)


def get_workspace_member_model():
    return apps.get_model(WORKSPACE_MEMBER_MODEL)


def get_comment_model():
    return apps.get_model(COMMENT_MODEL)


def memberships_for(user):
    """Membership rows of ``user``; empty for anonymous users."""
    member_model = get_workspace_member_model()
    if not getattr(user, "is_authenticated", False):
        return member_model.objects.none()
    return member_model.objects.filter(user=user)


def accessible_workspace_ids(user):
    """Lazy ``values_list`` of workspace ids the user belongs to (used as a SQL subquery)."""
    return memberships_for(user).values_list("workspace_id", flat=True)


def get_role(user, workspace_id):
    """The user's role in a workspace, or None if they are not a member."""
    return memberships_for(user).filter(workspace_id=workspace_id).values_list("role", flat=True).first()
