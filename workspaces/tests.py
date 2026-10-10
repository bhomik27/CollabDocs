from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Workspace, WorkspaceMember

User = get_user_model()
PW = "StrongPass#123"


class WorkspaceFlowTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@x.com", PW)
        self.viewer = User.objects.create_user("viewer", "viewer@x.com", PW)

    def test_register_and_login(self):
        r = self.client.post("/api/users/", {"username": "newuser", "email": "n@x.com", "password": PW})
        self.assertEqual(r.status_code, 201)
        self.assertIn("token", r.data)
        r = self.client.post("/api/users/login/", {"username": "newuser", "password": PW})
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/users/login/", {"username": "newuser", "password": "bad"})
        self.assertEqual(r.status_code, 401)

    def test_duplicate_email_is_400(self):
        r = self.client.post("/api/users/", {"username": "u2", "email": "owner@x.com", "password": PW})
        self.assertEqual(r.status_code, 400)

    def test_create_workspace_adds_admin_member(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post("/api/workspaces/", {"name": "My Space"})
        self.assertEqual(r.status_code, 201)
        m = WorkspaceMember.objects.get(workspace_id=r.data["id"], user=self.owner)
        self.assertEqual(m.role, WorkspaceMember.Role.ADMIN)

    def test_add_member_duplicate_returns_409(self):
        self.client.force_authenticate(self.owner)
        ws = self.client.post("/api/workspaces/", {"name": "My Space"}).data["id"]
        url = f"/api/workspaces/{ws}/members/"
        self.assertEqual(self.client.post(url, {"email": "viewer@x.com", "role": "editor"}).status_code, 201)
        self.assertEqual(self.client.post(url, {"email": "viewer@x.com"}).status_code, 409)
        self.assertEqual(self.client.post(url, {"email": "nobody@x.com"}).status_code, 404)

    def test_viewer_cannot_update_and_stats_work(self):
        self.client.force_authenticate(self.owner)
        ws = self.client.post("/api/workspaces/", {"name": "My Space"}).data["id"]
        self.client.post(f"/api/workspaces/{ws}/members/", {"email": "viewer@x.com", "role": "viewer"})
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.patch(f"/api/workspaces/{ws}/", {"name": "Hacked"}).status_code, 403)
        r = self.client.get(f"/api/workspaces/{ws}/stats/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.data["total_members"], r.data["admins"], r.data["viewers"]), (2, 1, 1))

    def test_non_member_gets_404_and_list_filters(self):
        self.client.force_authenticate(self.owner)
        ws = self.client.post("/api/workspaces/", {"name": "Alpha Team"}).data["id"]
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(f"/api/workspaces/{ws}/").status_code, 404)
        self.client.force_authenticate(self.owner)
        self.assertEqual(len(self.client.get("/api/workspaces/?search=alpha").data), 1)
        self.assertEqual(len(self.client.get("/api/workspaces/?search=zzz").data), 0)

    def test_duplicate_workspace_name_is_400(self):
        self.client.force_authenticate(self.owner)
        self.client.post("/api/workspaces/", {"name": "Same"})
        self.assertEqual(self.client.post("/api/workspaces/", {"name": "same"}).status_code, 400)
