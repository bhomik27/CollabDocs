from django.urls import reverse

from core.testing import BaseAPITestCase
from comments.models import Comment
from tags.models import DocumentTag, Tag

from .models import AuditLog
from .registry import registered_models


class AuditSignalTests(BaseAPITestCase):
    """Entries are written by signals, with the right actor, workspace and diff."""

    def test_person_c_models_are_registered(self):
        for model in (Comment, Tag, DocumentTag):
            self.assertIn(model, registered_models())

    def test_create_via_api_records_actor_workspace_and_values(self):
        self.login("editor")
        res = self.client.post(reverse("document-comments", args=[self.doc.pk]), {"body": "hello"})
        entry = AuditLog.objects.get()  # exactly one row: AuditLog does not audit itself
        self.assertEqual(entry.action, "create")
        self.assertEqual(entry.target_type, "comment")
        self.assertEqual(entry.target_id, str(res.data["id"]))
        self.assertEqual(entry.workspace_id, self.ws.pk)
        self.assertEqual(entry.actor, self.users["editor"])  # proves the middleware/contextvar trick works
        self.assertEqual(entry.changes["body"], "hello")

    def test_update_records_only_changed_fields_as_from_to(self):
        c = Comment.objects.create(document=self.doc, author=self.users["editor"], body="old")
        AuditLog.objects.all().delete()
        self.login("editor")
        self.client.patch(reverse("comment-detail", args=[c.pk]), {"body": "new"})
        entry = AuditLog.objects.get()
        self.assertEqual(entry.action, "update")
        self.assertEqual(entry.changes, {"body": {"from": "old", "to": "new"}})

    def test_save_with_no_changes_writes_nothing(self):
        c = Comment.objects.create(document=self.doc, author=self.users["editor"], body="same")
        AuditLog.objects.all().delete()
        c.save()
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_delete_records_final_values(self):
        c = Comment.objects.create(document=self.doc, author=self.users["editor"], body="bye")
        AuditLog.objects.all().delete()
        pk = c.pk
        self.login("editor")
        self.client.delete(reverse("comment-detail", args=[pk]))
        entry = AuditLog.objects.get()
        self.assertEqual((entry.action, entry.target_id), ("delete", str(pk)))
        self.assertEqual(entry.changes["body"], "bye")

    def test_cascade_delete_logs_each_reply(self):
        top = Comment.objects.create(document=self.doc, author=self.users["editor"], body="t")
        Comment.objects.create(document=self.doc, author=self.users["viewer"], body="r", parent=top, )
        AuditLog.objects.all().delete()
        top.delete()
        self.assertEqual(AuditLog.objects.filter(action="delete").count(), 2)

    def test_orm_change_without_request_has_no_actor(self):
        Comment.objects.create(document=self.doc, author=self.users["editor"], body="x")
        self.assertIsNone(AuditLog.objects.get().actor)

    def test_tag_attach_and_detach_are_logged(self):
        t = Tag.objects.create(workspace=self.ws, name="t")
        AuditLog.objects.all().delete()
        self.login("editor")
        self.client.post(reverse("document-tag-attach", args=[self.doc.pk]), {"tag_id": t.pk})
        self.client.delete(reverse("document-tag-detach", args=[self.doc.pk, t.pk]))
        self.assertEqual(list(AuditLog.objects.order_by("id").values_list("action", "target_type")),
                         [("create", "documenttag"), ("delete", "documenttag")])

    def test_failed_request_leaves_no_audit_row(self):
        self.login("editor")
        self.client.post(reverse("document-comments", args=[self.doc.pk]), {"body": ""})  # 400
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_person_a_and_b_models_are_registered(self):
        from documents.models import Document
        from workspaces.models import Workspace, WorkspaceMember

        for model in (Workspace, WorkspaceMember, Document):
            self.assertIn(model, registered_models())

    def test_user_deleting_own_account_cascades_with_null_actor(self):
        """Workspace.owner cascades into audited rows; their actor must not be the deleted user."""
        owner = self.users["owner"]
        Comment.objects.create(document=self.doc, author=self.users["editor"], body="x")
        AuditLog.objects.all().delete()
        self.login("owner")
        res = self.client.delete(reverse("user-detail", args=[owner.pk]))
        self.assertEqual(res.status_code, 204)
        deletes = AuditLog.objects.filter(action="delete")
        self.assertEqual(
            set(deletes.values_list("target_type", flat=True)),
            {"workspace", "workspacemember", "document", "comment"},
        )
        self.assertFalse(deletes.exclude(actor=None).exists())

    def test_audit_entries_cannot_be_modified(self):
        entry = AuditLog.objects.create(action="create", target_type="x", target_id=1)
        entry.action = "delete"
        with self.assertRaises(RuntimeError):
            entry.save()


class AuditApiTests(BaseAPITestCase):
    def setUp(self):
        c = Comment.objects.create(document=self.doc, author=self.users["editor"], body="x")
        c.delete()
        self.url = reverse("workspace-audit-logs", args=[self.ws.pk])

    def test_admin_and_owner_can_list_editor_cannot_outsider_404(self):
        for role in ("admin", "owner"):
            self.login(role)
            self.assertEqual(self.client.get(self.url).status_code, 200)
        self.login("editor")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.login("outsider")
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_filters(self):
        self.login("admin")
        self.assertEqual(self.client.get(self.url, {"action": "delete"}).data["count"], 1)
        self.assertEqual(self.client.get(self.url, {"target_type": "tag"}).data["count"], 0)
        self.assertEqual(self.client.get(self.url, {"created_after": "2000-01-01"}).data["count"], 2)
        self.assertEqual(self.client.get(self.url, {"created_before": "2000-01-01"}).data["count"], 0)

    def test_bad_date_is_400(self):
        self.login("admin")
        self.assertEqual(self.client.get(self.url, {"created_after": "yesterday"}).status_code, 400)

    def test_list_is_newest_first(self):
        self.login("admin")
        actions = [r["action"] for r in self.client.get(self.url).data["results"]]
        self.assertEqual(actions, ["delete", "create"])

    def test_workspaces_are_isolated(self):
        self.login("other_owner")
        res = self.client.get(reverse("workspace-audit-logs", args=[self.other_ws.pk]))
        self.assertEqual(res.data["count"], 0)

    def test_detail_admin_only(self):
        entry = AuditLog.objects.filter(workspace_id=self.ws.pk).first()
        url = reverse("audit-log-detail", args=[entry.pk])
        self.login("admin")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.login("editor")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_api_has_no_write_methods(self):
        self.login("owner")
        self.assertEqual(self.client.post(self.url, {}).status_code, 405)
        entry = AuditLog.objects.first()
        url = reverse("audit-log-detail", args=[entry.pk])
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(self.client.patch(url, {}).status_code, 405)
