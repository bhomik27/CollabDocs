"""
Shared test fixture for Person C's tests.

Builds two workspaces and one user per role so every permission rule can be tested:
  workspace 1: owner, admin, editor, viewer   (+ document `doc`)
  workspace 2: other_owner                    (+ document `other_doc`)
  outsider: belongs to no workspace
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from documents.models import Document
from workspaces.models import Membership, Workspace


class BaseAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.ws = Workspace.objects.create(name="Team")
        cls.other_ws = Workspace.objects.create(name="Other")
        cls.users = {}
        for role in ("owner", "admin", "editor", "viewer"):
            user = User.objects.create_user(username=role, password="x")
            Membership.objects.create(workspace=cls.ws, user=user, role=role)
            cls.users[role] = user
        cls.outsider = User.objects.create_user(username="outsider", password="x")
        cls.other_owner = User.objects.create_user(username="other_owner", password="x")
        Membership.objects.create(workspace=cls.other_ws, user=cls.other_owner, role="owner")
        cls.doc = Document.objects.create(workspace=cls.ws, title="Plan")
        cls.other_doc = Document.objects.create(workspace=cls.other_ws, title="Secret")

    def login(self, who):
        """Authenticate the test client as a role name ('editor'), 'outsider' or 'other_owner'."""
        user = self.users.get(who) or getattr(self, who)
        self.client.force_authenticate(user)
        return user
