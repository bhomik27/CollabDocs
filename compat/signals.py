"""
TEMPORARY audit signal -- stand-in for Person C's Document post_save signal.

It is connected only from ``CompatConfig.ready()``, so removing the ``compat``
app from INSTALLED_APPS removes this receiver too. Do NOT copy it into the
integrated project: Person C's receiver replaces it, otherwise every save
would be audited twice.

The write uses the default connection, so when a document is saved inside
``transaction.atomic()`` (as every document write path does) the audit row is
committed or rolled back together with the document and its version.
"""

from django.db.models.signals import post_save


def log_document_save(sender, instance, created, **kwargs):
    from compat.models import AuditLog

    AuditLog.objects.create(
        actor_id=instance.created_by_id,
        action="created" if created else "updated",
        model_name="Document",
        object_id=str(instance.pk),
    )


def connect():
    from documents.models import Document

    post_save.connect(log_document_save, sender=Document, dispatch_uid="compat_document_audit_log")
