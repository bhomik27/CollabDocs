"""
Rollback and audit-signal tests. TransactionTestCase is used so that the
service layer's transaction.atomic() is a real top-level transaction that
commits or rolls back, not a savepoint inside the test's own transaction.
"""

from unittest import mock

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APIClient, APITransactionTestCase

from documents import services
from documents.models import Document, DocumentVersion
from documents.tests.factories import add_member, audit_log_model, make_document, make_user, make_workspace


class FailingVersionCreate(Exception):
    pass


class RollbackTests(APITransactionTestCase):
    def setUp(self):
        self.user = make_user()
        self.workspace = make_workspace()
        add_member(self.workspace, self.user, "editor")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_rolls_back_document_and_audit_row_if_version_creation_fails(self):
        audit_rows_before = audit_log_model().objects.count()  # workspace + membership rows from setUp
        with self.assertLogs("documents", "ERROR"), mock.patch.object(DocumentVersion.objects, "create", side_effect=FailingVersionCreate("boom")):
            response = self.client.post(
                "/api/documents/", {"title": "T", "content": "c", "workspace": str(self.workspace.pk)}, format="json"
            )
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data, {"detail": "An unexpected error occurred.", "code": "server_error"})
        self.assertNotIn("boom", str(response.content))
        self.assertFalse(Document.objects.exists())
        self.assertEqual(audit_log_model().objects.count(), audit_rows_before)

    def test_update_rolls_back_if_version_creation_fails(self):
        document = make_document(self.workspace, self.user, title="Keep", content="original")
        audit_rows_before = audit_log_model().objects.count()
        with self.assertLogs("documents", "ERROR"), mock.patch.object(DocumentVersion.objects, "create", side_effect=FailingVersionCreate("boom")):
            response = self.client.patch(f"/api/documents/{document.pk}/", {"content": "lost"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        document.refresh_from_db()
        self.assertEqual(document.content, "original")
        self.assertEqual(document.versions.count(), 1)
        self.assertEqual(audit_log_model().objects.count(), audit_rows_before)

    def test_duplicate_version_number_returns_409_and_rolls_back(self):
        document = make_document(self.workspace, self.user, content="original")
        # Simulate a writer that bypassed the lock: count()+1 now collides with version 1.
        with self.assertLogs("documents", "WARNING"), mock.patch("documents.services.next_version_number", return_value=1):
            response = self.client.patch(f"/api/documents/{document.pk}/", {"content": "dup"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "version_conflict")
        document.refresh_from_db()
        self.assertEqual(document.content, "original")
        self.assertEqual(list(document.versions.values_list("version_number", flat=True)), [1])

    def test_restore_rolls_back_if_version_creation_fails(self):
        document = make_document(self.workspace, self.user, content="c1")
        services.update_document(document.pk, user=self.user, content="c2")
        v1 = document.versions.get(version_number=1)
        with self.assertLogs("documents", "ERROR"), mock.patch.object(DocumentVersion.objects, "create", side_effect=FailingVersionCreate("boom")):
            response = self.client.post(f"/api/documents/{document.pk}/versions/{v1.pk}/restore/")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        document.refresh_from_db()
        self.assertEqual(document.content, "c2")
        self.assertEqual(document.versions.count(), 2)


class VersionConstraintTests(APITransactionTestCase):
    def test_database_rejects_duplicate_version_numbers(self):
        user = make_user()
        document = make_document(make_workspace(), user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentVersion.objects.create(document=document, content="x", version_number=1, saved_by=user)

    def test_database_rejects_version_zero(self):
        user = make_user()
        document = make_document(make_workspace(), user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentVersion.objects.create(document=document, content="x", version_number=0, saved_by=user)


class AuditSignalCompatibilityTests(APITransactionTestCase):
    """
    Checks the contract with Person C's audit app: exactly one AuditLog row per
    document save, action create/update, target_type "document",
    target_id = str(uuid), actor = the user making the request, written in the
    same transaction as the change.
    """

    def setUp(self):
        self.creator = make_user("creator")
        self.editor = make_user("editor2")
        self.workspace = make_workspace()
        add_member(self.workspace, self.creator, "admin")
        add_member(self.workspace, self.editor, "editor")
        self.client = APIClient()

    def document_rows(self, **filters):
        return audit_log_model().objects.filter(target_type="document", **filters).order_by("id")

    def test_create_and_update_write_one_audit_row_each(self):
        self.client.force_authenticate(self.creator)
        response = self.client.post(
            "/api/documents/", {"title": "T", "content": "c", "workspace": str(self.workspace.pk)}, format="json"
        )
        doc_id = response.data["id"]
        self.client.force_authenticate(self.editor)
        self.client.patch(f"/api/documents/{doc_id}/", {"content": "c2"}, format="json")

        rows = list(self.document_rows().values_list("action", "target_id", "workspace_id", "actor_id"))
        self.assertEqual(
            rows,
            [
                ("create", str(doc_id), self.workspace.pk, self.creator.pk),
                ("update", str(doc_id), self.workspace.pk, self.editor.pk),
            ],
        )
        self.assertEqual(self.document_rows(action="update").get().changes, {"content": {"from": "c", "to": "c2"}})

    def test_restore_writes_update_audit_row(self):
        document = make_document(self.workspace, self.creator, content="c1")
        services.update_document(document.pk, user=self.creator, content="c2")
        v1 = document.versions.get(version_number=1)
        self.client.force_authenticate(self.editor)
        self.client.post(f"/api/documents/{document.pk}/versions/{v1.pk}/restore/")
        actions = list(self.document_rows(target_id=str(document.pk)).values_list("action", flat=True))
        self.assertEqual(actions, ["create", "update", "update"])
