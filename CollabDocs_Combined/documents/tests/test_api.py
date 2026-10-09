import uuid
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from documents.models import Document, DocumentVersion
from documents.tests.factories import (
    add_comment,
    add_member,
    make_document,
    make_user,
    make_workspace,
    tag_document,
)

LIST_URL = "/api/documents/"


def detail_url(doc_id):
    return f"/api/documents/{doc_id}/"


def versions_url(doc_id):
    return f"/api/documents/{doc_id}/versions/"


def version_url(doc_id, version_id):
    return f"/api/documents/{doc_id}/versions/{version_id}/"


def restore_url(doc_id, version_id):
    return f"/api/documents/{doc_id}/versions/{version_id}/restore/"


class DocumentAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user("admin")
        cls.editor = make_user("editor")
        cls.viewer = make_user("viewer")
        cls.outsider = make_user("outsider")
        cls.workspace = make_workspace("Main")
        cls.other_workspace = make_workspace("Other")
        add_member(cls.workspace, cls.admin, "admin")
        add_member(cls.workspace, cls.editor, "editor")
        add_member(cls.workspace, cls.viewer, "viewer")
        add_member(cls.other_workspace, cls.outsider, "admin")

    def as_user(self, user):
        self.client.force_authenticate(user)


class CreateDocumentTests(DocumentAPITestCase):
    def test_create_returns_201_and_creates_version_1(self):
        self.as_user(self.editor)
        response = self.client.post(
            LIST_URL, {"title": "Spec", "content": "Hello", "workspace": str(self.workspace.pk)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["version_count"], 1)
        self.assertEqual(response.data["created_by"]["username"], "editor")

        document = Document.objects.get(pk=response.data["id"])
        self.assertEqual(document.created_by, self.editor)
        version = document.versions.get()
        self.assertEqual(version.version_number, 1)
        self.assertEqual(version.content, "Hello")
        self.assertEqual(version.saved_by, self.editor)

    def test_viewer_cannot_create(self):
        self.as_user(self.viewer)
        response = self.client.post(LIST_URL, {"title": "X", "content": "", "workspace": str(self.workspace.pk)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Document.objects.exists())

    def test_cannot_create_in_workspace_user_is_not_member_of(self):
        self.as_user(self.editor)
        response = self.client.post(
            LIST_URL, {"title": "X", "content": "", "workspace": str(self.other_workspace.pk)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workspace", response.data)
        self.assertFalse(Document.objects.exists())

    def test_validation_errors_are_field_level(self):
        self.as_user(self.editor)
        response = self.client.post(
            LIST_URL,
            {"title": "   ", "workspace": "not-a-uuid", "status": "deleted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data), {"title", "workspace", "status", "content"})
        self.assertIn("not a valid status", str(response.data["status"][0]))

    def test_server_controlled_fields_are_rejected(self):
        self.as_user(self.editor)
        response = self.client.post(
            LIST_URL,
            {
                "title": "X", "content": "", "workspace": str(self.workspace.pk),
                "created_by": self.admin.pk, "version_number": 7,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("created_by", response.data)
        self.assertIn("version_number", response.data)

    def test_versions_number_independently_per_document(self):
        self.as_user(self.editor)
        doc_a = make_document(self.workspace, self.editor, title="A")
        doc_b = make_document(self.workspace, self.editor, title="B")
        for i in range(2):
            self.client.patch(detail_url(doc_a.pk), {"content": f"A{i}"}, format="json")
        self.client.patch(detail_url(doc_b.pk), {"content": "B1"}, format="json")
        self.assertEqual(list(doc_a.versions.values_list("version_number", flat=True)), [1, 2, 3])
        self.assertEqual(list(doc_b.versions.values_list("version_number", flat=True)), [1, 2])


class ListAndFilterTests(DocumentAPITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.d_draft = make_document(cls.workspace, cls.admin, title="Alpha plan", content="budget numbers")
        cls.d_pub = make_document(cls.workspace, cls.editor, title="Beta", content="the ALPHA release", status="published")
        cls.d_arch = make_document(cls.workspace, cls.editor, title="Gamma", content="old", status="archived")
        cls.hidden = make_document(cls.other_workspace, cls.outsider, title="Alpha secret")
        tag_document(cls.d_draft, "planning")
        tag_document(cls.d_draft, "backend")  # two tags: must not duplicate the row
        tag_document(cls.d_pub, "backend")

    def ids(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["id"] for row in response.data["results"]}

    def test_list_only_shows_accessible_workspaces(self):
        self.as_user(self.viewer)
        response = self.client.get(LIST_URL)
        self.assertEqual(self.ids(response), {str(d.pk) for d in (self.d_draft, self.d_pub, self.d_arch)})
        self.assertNotIn("content", response.data["results"][0])
        self.assertEqual(response.data["results"][0]["version_count"], 1)

    def test_filter_by_workspace_status_and_status_in(self):
        self.as_user(self.viewer)
        self.assertEqual(self.ids(self.client.get(LIST_URL, {"workspace": self.workspace.pk})), {str(self.d_draft.pk), str(self.d_pub.pk), str(self.d_arch.pk)})
        self.assertEqual(self.ids(self.client.get(LIST_URL, {"workspace": self.other_workspace.pk})), set())
        self.assertEqual(self.ids(self.client.get(LIST_URL, {"status": "published"})), {str(self.d_pub.pk)})
        self.assertEqual(
            self.ids(self.client.get(LIST_URL, {"status_in": "draft,archived"})), {str(self.d_draft.pk), str(self.d_arch.pk)}
        )

    def test_search_matches_title_or_content_case_insensitively(self):
        self.as_user(self.viewer)
        self.assertEqual(self.ids(self.client.get(LIST_URL, {"search": "alpha"})), {str(self.d_draft.pk), str(self.d_pub.pk)})

    def test_tag_filter_returns_distinct_documents(self):
        self.as_user(self.viewer)
        response = self.client.get(LIST_URL, {"tag": "backend"})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(self.ids(response), {str(self.d_draft.pk), str(self.d_pub.pk)})
        draft_row = next(r for r in response.data["results"] if r["id"] == str(self.d_draft.pk))
        self.assertEqual(draft_row["tags"], ["backend", "planning"])
        self.assertEqual(draft_row["version_count"], 1)

    def test_filter_by_creator(self):
        self.as_user(self.viewer)
        self.assertEqual(self.ids(self.client.get(LIST_URL, {"created_by": self.admin.pk})), {str(self.d_draft.pk)})

    def test_updated_after_and_before(self):
        past = timezone.now() - timedelta(days=10)
        Document.objects.filter(pk=self.d_arch.pk).update(updated_at=past)
        self.as_user(self.viewer)
        cutoff = (timezone.now() - timedelta(days=1)).date().isoformat()
        self.assertEqual(self.ids(self.client.get(LIST_URL, {"updated_before": cutoff})), {str(self.d_arch.pk)})
        self.assertEqual(
            self.ids(self.client.get(LIST_URL, {"updated_after": cutoff})), {str(self.d_draft.pk), str(self.d_pub.pk)}
        )

    def test_malformed_query_parameters_return_400(self):
        self.as_user(self.viewer)
        cases = {
            "workspace": "nope",
            "status": "deleted",
            "status_in": "draft,bogus",
            "created_by": "abc",
            "updated_after": "yesterday",
            "updated_before": "2026-02-30",
        }
        for param, value in cases.items():
            with self.subTest(param=param):
                response = self.client.get(LIST_URL, {param: value})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(param, response.data)

    def test_inverted_date_range_returns_400(self):
        self.as_user(self.viewer)
        response = self.client.get(LIST_URL, {"updated_after": "2026-05-01", "updated_before": "2026-04-01"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("updated_before", response.data)


class RetrieveTests(DocumentAPITestCase):
    def test_retrieve_document(self):
        doc = make_document(self.workspace, self.admin, title="R", content="body")
        tag_document(doc, "planning")
        self.as_user(self.viewer)
        response = self.client.get(detail_url(doc.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["content"], "body")
        self.assertEqual(response.data["tags"], ["planning"])
        self.assertEqual(response.data["version_count"], 1)

    def test_missing_malformed_and_foreign_documents_are_404(self):
        foreign = make_document(self.other_workspace, self.outsider)
        self.as_user(self.admin)
        for url in (detail_url(uuid.uuid4()), detail_url("not-a-uuid"), detail_url(foreign.pk)):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)


class UpdateTests(DocumentAPITestCase):
    def setUp(self):
        self.doc = make_document(self.workspace, self.admin, title="Original", content="v1")

    def test_put_updates_and_creates_version(self):
        self.as_user(self.editor)
        response = self.client.put(
            detail_url(self.doc.pk), {"title": "New", "content": "v2", "status": "published"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["version_count"], 2)
        self.doc.refresh_from_db()
        self.assertEqual((self.doc.title, self.doc.content, self.doc.status), ("New", "v2", "published"))
        latest = self.doc.versions.order_by("-version_number").first()
        self.assertEqual((latest.version_number, latest.content, latest.saved_by), (2, "v2", self.editor))
        # created_by is not changed by an update
        self.assertEqual(self.doc.created_by, self.admin)

    def test_put_requires_full_representation(self):
        self.as_user(self.editor)
        response = self.client.put(detail_url(self.doc.pk), {"title": "Only title"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("content", response.data)
        self.assertEqual(self.doc.versions.count(), 1)

    def test_patch_preserves_content_when_omitted(self):
        self.as_user(self.editor)
        response = self.client.patch(detail_url(self.doc.pk), {"status": "archived"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doc.refresh_from_db()
        self.assertEqual((self.doc.content, self.doc.status), ("v1", "archived"))
        self.assertEqual(list(self.doc.versions.values_list("version_number", "content")), [(1, "v1"), (2, "v1")])

    def test_patch_content_creates_version(self):
        self.as_user(self.editor)
        self.client.patch(detail_url(self.doc.pk), {"content": "v2"}, format="json")
        self.client.patch(detail_url(self.doc.pk), {"content": "v3"}, format="json")
        self.assertEqual(list(self.doc.versions.values_list("version_number", "content")), [(1, "v1"), (2, "v2"), (3, "v3")])

    def test_cannot_move_document_to_another_workspace(self):
        add_member(self.other_workspace, self.editor, "editor")
        self.as_user(self.editor)
        response = self.client.patch(detail_url(self.doc.pk), {"workspace": str(self.other_workspace.pk)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workspace", response.data)

    def test_viewer_cannot_update(self):
        self.as_user(self.viewer)
        response = self.client.patch(detail_url(self.doc.pk), {"content": "hack"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.content, "v1")
        self.assertEqual(self.doc.versions.count(), 1)

    def test_non_member_update_is_404(self):
        self.as_user(self.outsider)
        response = self.client.patch(detail_url(self.doc.pk), {"content": "hack"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_status_on_update(self):
        self.as_user(self.editor)
        response = self.client.patch(detail_url(self.doc.pk), {"status": "gone"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)


class DeleteTests(DocumentAPITestCase):
    def test_admin_deletes_document_and_versions_cascade(self):
        doc = make_document(self.workspace, self.editor)
        self.as_user(self.admin)
        response = self.client.delete(detail_url(doc.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())
        self.assertFalse(DocumentVersion.objects.filter(document_id=doc.pk).exists())
        self.assertEqual(self.client.get(detail_url(doc.pk)).status_code, status.HTTP_404_NOT_FOUND)

    def test_editor_can_delete_own_document_only(self):
        own = make_document(self.workspace, self.editor)
        others = make_document(self.workspace, self.admin)
        self.as_user(self.editor)
        self.assertEqual(self.client.delete(detail_url(others.pk)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(detail_url(own.pk)).status_code, status.HTTP_204_NO_CONTENT)

    def test_viewer_cannot_delete(self):
        doc = make_document(self.workspace, self.admin)
        self.as_user(self.viewer)
        self.assertEqual(self.client.delete(detail_url(doc.pk)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Document.objects.filter(pk=doc.pk).exists())


class VersionEndpointTests(DocumentAPITestCase):
    def setUp(self):
        self.doc = make_document(self.workspace, self.admin, content="c1")
        self.as_user(self.editor)
        for n in range(2, 6):
            self.client.patch(detail_url(self.doc.pk), {"content": f"c{n}"}, format="json")
        self.versions = {v.version_number: v for v in self.doc.versions.all()}

    def test_version_history_is_ascending(self):
        self.as_user(self.viewer)
        response = self.client.get(versions_url(self.doc.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([v["version_number"] for v in response.data], [1, 2, 3, 4, 5])
        self.assertNotIn("content", response.data[0])

    def test_version_detail(self):
        self.as_user(self.viewer)
        response = self.client.get(version_url(self.doc.pk, self.versions[2].pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.data["version_number"], response.data["content"]), (2, "c2"))
        self.assertEqual(response.data["document"], self.doc.pk)

    def test_version_detail_404s(self):
        other_doc = make_document(self.workspace, self.admin)
        other_version = other_doc.versions.get()
        self.as_user(self.viewer)
        cases = {
            "missing version": version_url(self.doc.pk, uuid.uuid4()),
            "malformed version": version_url(self.doc.pk, "not-a-uuid"),
            "version of another document": version_url(self.doc.pk, other_version.pk),
            "missing document": version_url(uuid.uuid4(), self.versions[1].pk),
            "malformed document": versions_url("nope"),
        }
        for label, url in cases.items():
            with self.subTest(label):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_restore_creates_new_version_and_preserves_history(self):
        response = self.client.post(restore_url(self.doc.pk, self.versions[2].pk))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["version"]["version_number"], 6)
        self.assertEqual(response.data["version"]["content"], "c2")
        self.assertEqual(response.data["version"]["restored_from"], self.versions[2].pk)
        self.assertEqual(response.data["restored_from_version"], 2)
        self.assertEqual(response.data["document"]["content"], "c2")
        self.assertEqual(response.data["document"]["version_count"], 6)

        self.doc.refresh_from_db()
        self.assertEqual(self.doc.content, "c2")
        history = list(self.doc.versions.values_list("version_number", "content"))
        self.assertEqual(history, [(1, "c1"), (2, "c2"), (3, "c3"), (4, "c4"), (5, "c5"), (6, "c2")])

    def test_restore_rejects_version_of_another_document(self):
        other_doc = make_document(self.workspace, self.admin, content="other")
        response = self.client.post(restore_url(self.doc.pk, other_doc.versions.get().pk))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.doc.versions.count(), 5)

    def test_restore_invalid_version_ids(self):
        for version_id in (uuid.uuid4(), "garbage"):
            with self.subTest(version_id=version_id):
                self.assertEqual(self.client.post(restore_url(self.doc.pk, version_id)).status_code, 404)

    def test_viewer_cannot_restore(self):
        self.as_user(self.viewer)
        response = self.client.post(restore_url(self.doc.pk, self.versions[1].pk))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.doc.versions.count(), 5)

    def test_non_member_cannot_see_versions(self):
        self.as_user(self.outsider)
        self.assertEqual(self.client.get(versions_url(self.doc.pk)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(version_url(self.doc.pk, self.versions[1].pk)).status_code, 404)
        self.assertEqual(self.client.post(restore_url(self.doc.pk, self.versions[1].pk)).status_code, 404)


class StatsTests(DocumentAPITestCase):
    def test_stats_counts_without_join_inflation(self):
        doc = make_document(self.workspace, self.admin, content="a")
        self.as_user(self.editor)
        self.client.patch(detail_url(doc.pk), {"content": "b"}, format="json")
        self.client.patch(detail_url(doc.pk), {"content": "c"}, format="json")
        add_comment(doc, self.viewer)
        add_comment(doc, self.viewer)
        add_comment(doc, self.editor)  # editor both edited and commented: counted once
        make_document(self.workspace, self.viewer)  # unrelated document

        self.as_user(self.viewer)
        response = self.client.get(f"/api/documents/{doc.pk}/stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version_count"], 3)
        self.assertEqual(response.data["latest_version_number"], 3)
        self.assertEqual(response.data["comment_count"], 3)
        self.assertEqual(response.data["contributor_count"], 3)  # admin, editor, viewer

    def test_stats_for_inaccessible_document_is_404(self):
        doc = make_document(self.other_workspace, self.outsider)
        self.as_user(self.viewer)
        self.assertEqual(self.client.get(f"/api/documents/{doc.pk}/stats/").status_code, 404)


class AuthenticationTests(DocumentAPITestCase):
    def test_unauthenticated_requests_are_rejected(self):
        doc = make_document(self.workspace, self.admin)
        version = doc.versions.get()
        requests = [
            ("get", LIST_URL), ("post", LIST_URL), ("get", detail_url(doc.pk)), ("put", detail_url(doc.pk)),
            ("patch", detail_url(doc.pk)), ("delete", detail_url(doc.pk)), ("get", versions_url(doc.pk)),
            ("get", version_url(doc.pk, version.pk)), ("post", restore_url(doc.pk, version.pk)),
            ("get", f"/api/documents/{doc.pk}/stats/"),
        ]
        for method, url in requests:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(Document.objects.filter(pk=doc.pk).exists())

    def test_token_authentication(self):
        token = Token.objects.create(user=self.viewer)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION="Token wrong")
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_401_UNAUTHORIZED)
