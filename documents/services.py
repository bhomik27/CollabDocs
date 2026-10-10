"""
Write paths for documents. Every function here runs inside a single
``transaction.atomic()`` block, so a document change and its version snapshot
(and any post_save audit row written on the same connection) commit or roll
back together.

Version numbering and concurrency
---------------------------------
The next number is ``document.versions.count() + 1`` (assignment requirement).
That calculation is only safe if no other transaction can add a version to the
same document between the count and the insert, so every path that adds a
version to an *existing* document first takes a row lock on that document with
``select_for_update()``. On PostgreSQL concurrent writers to the same document
therefore queue up one after another; writers to different documents do not
block each other.

The ``unique_document_version_number`` constraint backs this up: if a number
is ever duplicated anyway (e.g. versions inserted outside these functions, or
history rows deleted manually so that count()+1 collides with an existing
number) the insert fails, the whole transaction rolls back, and the API
returns 409 instead of silently storing a duplicate.

SQLite ignores ``select_for_update()``; it serialises writers with a database
lock instead, so only PostgreSQL demonstrates the row-lock behaviour.
"""

import logging

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound

from documents.exceptions import VersionConflict
from documents.models import Document, DocumentVersion

logger = logging.getLogger("documents")


def next_version_number(document):
    return document.versions.count() + 1


def _record_version(document, version_number, user, restored_from=None):
    """Snapshot ``document.content`` as ``version_number``. Caller holds the row lock (or owns a new row)."""
    try:
        version = DocumentVersion.objects.create(
            document=document,
            content=document.content,
            version_number=version_number,
            saved_by=user,
            restored_from=restored_from,
        )
    except IntegrityError as exc:
        logger.warning("Version number conflict on document %s: %s", document.pk, exc)
        raise VersionConflict() from exc
    # Equals the version count because numbers are contiguous from 1.
    document.version_count = version.version_number
    return version


def _lock_document(document_id):
    try:
        return Document.objects.select_for_update().get(pk=document_id)
    except Document.DoesNotExist:
        # Deleted by a concurrent request after the permission check.
        raise NotFound("Document not found.")


def create_document(*, user, **fields):
    """Create a document and its version 1 atomically."""
    with transaction.atomic():
        document = Document.objects.create(created_by=user, **fields)
        version = _record_version(document, next_version_number(document), user)
    return document, version


def update_document(document_id, *, user, **changes):
    """
    Apply already-validated ``changes`` (from DocumentSerializer) to the locked
    document and record a new version atomically. Fields not in ``changes``
    keep their current values, so a PATCH without ``content`` preserves it.

    Steps: lock row -> next number = count() + 1 -> save document -> create version.
    The lock also prevents lost updates: a concurrent PATCH of another field
    re-reads the row after this transaction commits instead of overwriting it
    with stale values.
    """
    with transaction.atomic():
        document = _lock_document(document_id)
        version_number = next_version_number(document)
        for field, value in changes.items():
            setattr(document, field, value)
        document.save()
        version = _record_version(document, version_number, user)
    return document, version


def restore_version(document_id, version_id, *, user):
    """
    Copy an old version's content onto the document and record it as a NEW
    version. Existing history is never modified.
    """
    with transaction.atomic():
        document = _lock_document(document_id)
        try:
            source = document.versions.get(pk=version_id)
        except DocumentVersion.DoesNotExist:
            raise NotFound("Version not found for this document.")
        version_number = next_version_number(document)
        document.content = source.content
        document.save(update_fields=["content", "updated_at"])
        version = _record_version(document, version_number, user, restored_from=source)
    return document, version, source


def delete_document(document):
    """Delete a document; its versions go with it through on_delete=CASCADE."""
    with transaction.atomic():
        document.delete()
