"""
Shared test fixture for Person C's tests.

Builds two workspaces and one user per role so every permission rule can be tested:
  workspace 1: owner, admin, editor, viewer   (+ document `doc`)
  workspace 2: other_owner                    (+ document `other_doc`)
  outsider: belongs to no workspace

"owner" is Workspace.owner and, as in Person A's create flow, holds an admin membership.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from audit.models import AuditLog
from documents.models import Document
from workspaces.models import Workspace, WorkspaceMember


def make_user(username):
    # User.email is unique, so every fixture user needs its own address.
    return get_user_model().objects.create_user(username=username, email=f"{username}@example.com", password="x")


class BaseAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {role: make_user(role) for role in ("owner", "admin", "editor", "viewer")}
        cls.outsider = make_user("outsider")
        cls.other_owner = make_user("other_owner")

        cls.ws = Workspace.objects.create(name="Team", owner=cls.users["owner"])
        cls.other_ws = Workspace.objects.create(name="Other", owner=cls.other_owner)
        member_role = {"owner": WorkspaceMember.Role.ADMIN}
        for role, user in cls.users.items():
            WorkspaceMember.objects.create(workspace=cls.ws, user=user, role=member_role.get(role, role))
        WorkspaceMember.objects.create(workspace=cls.other_ws, user=cls.other_owner, role=WorkspaceMember.Role.ADMIN)

        cls.doc = Document.objects.create(workspace=cls.ws, title="Plan")
        cls.other_doc = Document.objects.create(workspace=cls.other_ws, title="Secret")

        # Workspaces, memberships and documents are audited too; start every test with an
        # empty log so assertions only see the rows the test itself caused.
        AuditLog.objects.all().delete()

    def login(self, who):
        """Authenticate the test client as a role name ('editor'), 'outsider' or 'other_owner'."""
        user = self.users.get(who) or getattr(self, who)
        self.client.force_authenticate(user)
        return user
