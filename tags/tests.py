from django.urls import reverse

from core.testing import BaseAPITestCase

from .models import DocumentTag, Tag


class TagTests(BaseAPITestCase):
    def url_ws(self, ws=None):
        return reverse("workspace-tags", args=[(ws or self.ws).pk])

    def tag(self, name="urgent", ws=None):
        return Tag.objects.create(workspace=ws or self.ws, name=name)

    # ---- list / create ----
    def test_member_lists_tags_with_document_counts(self):
        t = self.tag()
        DocumentTag.objects.create(document=self.doc, tag=t)
        self.login("viewer")
        res = self.client.get(self.url_ws())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["results"][0]["document_count"], 1)

    def test_non_member_gets_404(self):
        self.login("outsider")
        self.assertEqual(self.client.get(self.url_ws()).status_code, 404)

    def test_viewer_cannot_create_editor_can(self):
        self.login("viewer")
        self.assertEqual(self.client.post(self.url_ws(), {"name": "a"}).status_code, 403)
        self.login("editor")
        res = self.client.post(self.url_ws(), {"name": "a", "color": "#ff0000"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["color"], "#ff0000")
        self.assertEqual(res.data["document_count"], 0)

    def test_duplicate_name_rejected_but_ok_in_other_workspace(self):
        self.tag("dup")
        self.login("editor")
        self.assertEqual(self.client.post(self.url_ws(), {"name": "DUP"}).status_code, 400)  # case-insensitive
        self.login("other_owner")
        self.assertEqual(self.client.post(self.url_ws(self.other_ws), {"name": "dup"}).status_code, 201)

    def test_invalid_color_rejected(self):
        self.login("editor")
        self.assertEqual(self.client.post(self.url_ws(), {"name": "x", "color": "red"}).status_code, 400)

    # ---- detail ----
    def test_edit_and_delete_need_editor(self):
        t = self.tag()
        url = reverse("tag-detail", args=[t.pk])
        self.login("viewer")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.patch(url, {"name": "x"}).status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.login("editor")
        self.assertEqual(self.client.patch(url, {"name": "renamed"}).status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.name, "renamed")
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_rename_to_own_current_name_is_allowed_but_not_to_a_sibling(self):
        a, b = self.tag("a"), self.tag("b")
        self.login("editor")
        url = reverse("tag-detail", args=[a.pk])
        self.assertEqual(self.client.patch(url, {"name": "a"}).status_code, 200)
        self.assertEqual(self.client.patch(url, {"name": "b"}).status_code, 400)

    def test_outsider_cannot_see_tag(self):
        t = self.tag()
        self.login("other_owner")
        self.assertEqual(self.client.get(reverse("tag-detail", args=[t.pk])).status_code, 404)

    def test_deleting_tag_removes_its_links(self):
        t = self.tag()
        DocumentTag.objects.create(document=self.doc, tag=t)
        self.login("editor")
        self.client.delete(reverse("tag-detail", args=[t.pk]))
        self.assertEqual(DocumentTag.objects.count(), 0)

    # ---- attach / detach ----
    def attach_url(self, doc=None):
        return reverse("document-tag-attach", args=[(doc or self.doc).pk])

    def test_attach_is_idempotent(self):
        t = self.tag()
        self.login("editor")
        self.assertEqual(self.client.post(self.attach_url(), {"tag_id": t.pk}).status_code, 201)
        self.assertEqual(self.client.post(self.attach_url(), {"tag_id": t.pk}).status_code, 200)
        self.assertEqual(DocumentTag.objects.count(), 1)

    def test_cannot_attach_tag_from_another_workspace(self):
        foreign = self.tag("f", ws=self.other_ws)
        self.login("editor")
        res = self.client.post(self.attach_url(), {"tag_id": foreign.pk})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(DocumentTag.objects.count(), 0)

    def test_viewer_cannot_attach_or_detach(self):
        t = self.tag()
        DocumentTag.objects.create(document=self.doc, tag=t)
        self.login("viewer")
        self.assertEqual(self.client.post(self.attach_url(), {"tag_id": t.pk}).status_code, 403)
        self.assertEqual(self.client.delete(reverse("document-tag-detach", args=[self.doc.pk, t.pk])).status_code, 403)

    def test_outsider_gets_404_on_attach(self):
        t = self.tag()
        self.login("outsider")
        self.assertEqual(self.client.post(self.attach_url(), {"tag_id": t.pk}).status_code, 404)

    def test_detach_then_404(self):
        t = self.tag()
        DocumentTag.objects.create(document=self.doc, tag=t)
        self.login("editor")
        url = reverse("document-tag-detach", args=[self.doc.pk, t.pk])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(url).status_code, 404)
