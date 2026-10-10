from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import BaseAPITestCase

from .models import Comment


class CommentTests(BaseAPITestCase):
    def url_list(self, doc=None):
        return reverse("document-comments", args=[(doc or self.doc).pk])

    def make(self, author="editor", body="hi", parent=None, doc=None):
        return Comment.objects.create(document=doc or self.doc, author=self.users[author], body=body, parent=parent)

    # ---- list / create ----
    def test_list_nests_replies_under_parents(self):
        parent = self.make(body="top")
        self.make(author="viewer", body="reply", parent=parent)
        self.login("viewer")
        res = self.client.get(self.url_list())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)  # replies are not listed at top level
        top = res.data["results"][0]
        self.assertEqual(top["body"], "top")
        self.assertEqual([r["body"] for r in top["replies"]], ["reply"])
        self.assertEqual(top["author"], {"id": self.users["editor"].pk, "username": "editor"})

    def test_non_member_gets_404_not_403(self):
        self.login("outsider")
        self.assertEqual(self.client.get(self.url_list()).status_code, 404)
        self.assertEqual(self.client.post(self.url_list(), {"body": "x"}).status_code, 404)

    def test_other_workspace_document_is_invisible(self):
        self.login("editor")
        self.assertEqual(self.client.get(self.url_list(self.other_doc)).status_code, 404)

    def test_unauthenticated_is_rejected(self):
        self.assertIn(self.client.get(self.url_list()).status_code, (401, 403))

    def test_any_member_can_comment_and_author_is_set_from_login(self):
        self.login("viewer")
        res = self.client.post(self.url_list(), {"body": "hello", "author": self.users["owner"].pk})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Comment.objects.get(pk=res.data["id"]).author, self.users["viewer"])  # client's "author" ignored

    def test_blank_body_rejected(self):
        self.login("editor")
        self.assertEqual(self.client.post(self.url_list(), {"body": ""}).status_code, 400)

    def test_reply_works_and_reply_to_reply_is_rejected(self):
        top = self.make()
        self.login("editor")
        ok = self.client.post(self.url_list(), {"body": "r", "parent": top.pk})
        self.assertEqual(ok.status_code, 201)
        nested = self.client.post(self.url_list(), {"body": "rr", "parent": ok.data["id"]})
        self.assertEqual(nested.status_code, 400)
        self.assertIn("parent", nested.data)

    def test_parent_from_another_document_is_rejected(self):
        other = Comment.objects.create(document=self.other_doc, author=self.other_owner, body="x")
        self.login("editor")
        res = self.client.post(self.url_list(), {"body": "r", "parent": other.pk})
        self.assertEqual(res.status_code, 400)

    # ---- detail / edit / delete ----
    def test_retrieve_comment(self):
        c = self.make()
        self.login("viewer")
        self.assertEqual(self.client.get(reverse("comment-detail", args=[c.pk])).status_code, 200)
        self.login("outsider")
        self.assertEqual(self.client.get(reverse("comment-detail", args=[c.pk])).status_code, 404)

    def test_only_author_can_edit(self):
        c = self.make(author="editor", body="old")
        url = reverse("comment-detail", args=[c.pk])
        self.login("admin")  # even an admin may not edit someone else's words
        self.assertEqual(self.client.patch(url, {"body": "hacked"}).status_code, 403)
        self.login("editor")
        res = self.client.patch(url, {"body": "new"})
        self.assertEqual(res.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.body, "new")

    def test_edit_requires_body_and_cannot_move_comment(self):
        c = self.make()
        self.login("editor")
        url = reverse("comment-detail", args=[c.pk])
        self.assertEqual(self.client.patch(url, {}).status_code, 400)
        self.client.patch(url, {"body": "ok", "document": self.other_doc.pk})
        c.refresh_from_db()
        self.assertEqual(c.document_id, self.doc.pk)

    def test_put_is_not_allowed(self):
        c = self.make()
        self.login("editor")
        self.assertEqual(self.client.put(reverse("comment-detail", args=[c.pk]), {"body": "x"}).status_code, 405)

    def test_delete_rules(self):
        c = self.make(author="editor")
        url = reverse("comment-detail", args=[c.pk])
        self.login("viewer")
        self.assertEqual(self.client.delete(url).status_code, 403)   # other member
        self.login("admin")
        self.assertEqual(self.client.delete(url).status_code, 204)   # moderator
        c2 = self.make(author="editor")
        self.login("editor")
        self.assertEqual(self.client.delete(reverse("comment-detail", args=[c2.pk])).status_code, 204)  # author

    def test_deleting_parent_deletes_replies(self):
        top = self.make()
        self.make(author="viewer", parent=top)
        self.login("editor")
        self.client.delete(reverse("comment-detail", args=[top.pk]))
        self.assertEqual(Comment.objects.count(), 0)

    # ---- performance: the N+1 guard ----
    def test_list_query_count_does_not_grow_with_data(self):
        def count_queries():
            self.login("viewer")
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(self.url_list()).status_code, 200)
            return len(ctx)

        for i in range(2):
            p = self.make(body=f"p{i}")
            self.make(author="viewer", parent=p)
        small = count_queries()
        for i in range(15):
            p = self.make(author="admin", body=f"q{i}")
            self.make(author="owner", parent=p)
            self.make(author="viewer", parent=p)
        self.assertEqual(count_queries(), small)
