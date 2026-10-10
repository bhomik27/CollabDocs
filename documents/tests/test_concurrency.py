"""
Concurrency tests. They need real row locks, so they only run on PostgreSQL
(SQLite ignores select_for_update() and cannot demonstrate this).
"""

import threading
import time
from unittest import mock, skipUnless

from django.db import OperationalError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase

from documents import services
from documents.models import Document
from documents.tests.factories import make_document, make_user, make_workspace

requires_postgres = skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row locking")


@requires_postgres
class ConcurrentVersioningTests(TransactionTestCase):
    def setUp(self):
        self.user = make_user()
        self.document = make_document(make_workspace(), self.user, content="v1")

    def test_concurrent_updates_produce_unique_sequential_versions(self):
        writers = 12
        barrier = threading.Barrier(writers)
        errors = []

        def write(n):
            try:
                barrier.wait()  # start every writer at the same moment
                services.update_document(self.document.pk, user=self.user, content=f"writer {n}")
            except Exception as exc:  # collected and asserted below
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=write, args=(n,)) for n in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        self.assertEqual(errors, [])
        numbers = list(self.document.versions.order_by("version_number").values_list("version_number", flat=True))
        self.assertEqual(numbers, list(range(1, writers + 2)))

    def test_update_holds_row_lock_until_commit(self):
        locked = threading.Event()
        release = threading.Event()

        def hold_lock():
            try:
                with transaction.atomic():
                    Document.objects.select_for_update().get(pk=self.document.pk)
                    locked.set()
                    release.wait(timeout=30)
            finally:
                connections.close_all()

        holder = threading.Thread(target=hold_lock)
        holder.start()
        try:
            self.assertTrue(locked.wait(timeout=30))
            with self.assertRaises(OperationalError), transaction.atomic():
                # NOWAIT fails immediately because the other transaction holds the row lock.
                Document.objects.select_for_update(nowait=True).get(pk=self.document.pk)
        finally:
            release.set()
            holder.join(timeout=30)
        close_old_connections()

        # After the holder commits, a normal update proceeds.
        services.update_document(self.document.pk, user=self.user, content="after lock")
        self.assertEqual(self.document.versions.count(), 2)

    def test_concurrent_patches_of_different_fields_do_not_lose_updates(self):
        """
        Writer A changes content and is slow between reading and saving; writer
        B changes the title meanwhile. With the row lock, B reads the row only
        after A commits, so both changes survive.
        """
        a_has_row = threading.Event()
        original_save = Document.save

        def slow_save(instance, *args, **kwargs):
            if instance.content == "from A":
                a_has_row.set()
                time.sleep(0.5)  # give B every chance to read the stale row
            return original_save(instance, *args, **kwargs)

        def writer_a():
            try:
                services.update_document(self.document.pk, user=self.user, content="from A")
            finally:
                connections.close_all()

        def writer_b():
            try:
                a_has_row.wait(timeout=30)
                services.update_document(self.document.pk, user=self.user, title="from B")
            finally:
                connections.close_all()

        with mock.patch.object(Document, "save", slow_save):
            threads = [threading.Thread(target=writer_a), threading.Thread(target=writer_b)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)

        self.document.refresh_from_db()
        self.assertEqual((self.document.title, self.document.content), ("from B", "from A"))
        self.assertEqual(self.document.versions.count(), 3)

    def test_concurrent_restores_produce_unique_versions(self):
        services.update_document(self.document.pk, user=self.user, content="v2")
        v1 = self.document.versions.get(version_number=1)
        writers = 6
        barrier = threading.Barrier(writers)
        errors = []

        def restore():
            try:
                barrier.wait()
                services.restore_version(self.document.pk, v1.pk, user=self.user)
            except Exception as exc:
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=restore) for _ in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        self.assertEqual(errors, [])
        numbers = list(self.document.versions.order_by("version_number").values_list("version_number", flat=True))
        self.assertEqual(numbers, list(range(1, writers + 3)))
