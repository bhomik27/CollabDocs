"""
Query-count tests: each endpoint must run a constant number of queries no
matter how many documents / versions / tags it returns (no N+1).
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from documents import services
from documents.tests.factories import add_comment, add_member, make_document, make_user, make_workspace, tag_document


class QueryCountTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user()
        cls.workspace = make_workspace()
        add_member(cls.workspace, cls.user, "admin")

    def setUp(self):
        self.client.force_authenticate(self.user)

    def count_queries(self, method, url, **kwargs):
        with CaptureQueriesContext(connection) as ctx:
            response = getattr(self.client, method)(url, **kwargs)
        self.assertLess(response.status_code, 300, getattr(response, "data", None))
        return len(ctx.captured_queries), ctx.captured_queries

    def add_documents(self, n, versions_each=1, tags=("a", "b")):
        docs = []
        for i in range(n):
            doc = make_document(self.workspace, make_user(), title=f"doc {i}")
            for _ in range(versions_each - 1):
                services.update_document(doc.pk, user=self.user, content="more")
            for tag in tags:
                tag_document(doc, tag)
            docs.append(doc)
        return docs

    def test_document_list_query_count_is_constant(self):
        self.add_documents(2)
        small, _ = self.count_queries("get", "/api/documents/")
        self.add_documents(10, versions_each=3)
        large, queries = self.count_queries("get", "/api/documents/", data={"tag": "a", "search": "doc"})
        self.assertEqual(small, large)
        # paginator COUNT, the page query, and one tags prefetch
        self.assertEqual(large, 3, [q["sql"] for q in queries])
        page_sql = queries[1]["sql"].upper()
        self.assertIn("JOIN", page_sql)  # workspace and creator are fetched with select_related
        self.assertNotIn('"CONTENT"', page_sql.split(" FROM ")[0])  # document bodies are deferred in lists

    def test_retrieve_query_count(self):
        doc = self.add_documents(1, versions_each=4)[0]
        count, queries = self.count_queries("get", f"/api/documents/{doc.pk}/")
        self.assertEqual(count, 2, [q["sql"] for q in queries])  # document (+annotations) and tags

    def test_version_history_query_count_is_constant(self):
        doc = self.add_documents(1, versions_each=2)[0]
        small, _ = self.count_queries("get", f"/api/documents/{doc.pk}/versions/")
        for _ in range(8):
            services.update_document(doc.pk, user=make_user(), content="x")
        large, queries = self.count_queries("get", f"/api/documents/{doc.pk}/versions/")
        self.assertEqual(small, large)
        self.assertEqual(large, 2, [q["sql"] for q in queries])  # document permission lookup, versions + saved_by join

    def test_version_detail_query_count(self):
        doc = self.add_documents(1, versions_each=2)[0]
        version = doc.versions.get(version_number=2)
        count, queries = self.count_queries("get", f"/api/documents/{doc.pk}/versions/{version.pk}/")
        self.assertEqual(count, 2, [q["sql"] for q in queries])

    def test_stats_query_count(self):
        doc = self.add_documents(1, versions_each=3)[0]
        for _ in range(5):
            add_comment(doc, make_user())
        count, queries = self.count_queries("get", f"/api/documents/{doc.pk}/stats/")
        # document lookup, version aggregate, comment aggregate, contributor UNION count
        self.assertEqual(count, 4, [q["sql"] for q in queries])
