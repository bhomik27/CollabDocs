from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_delete, pre_delete


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"

    def ready(self):
        """Turn on auditing for Person C's models.

        Person A's and Person B's models are registered with the same one-liner in
        workspaces/apps.py and documents/apps.py. Forgetting this step fails silently:
        nothing is logged, nothing errors.
        """
        from audit import signals
        from audit.registry import register
        from comments.models import Comment
        from tags.models import DocumentTag, Tag

        register(Comment, lambda c: c.document.workspace_id)
        register(Tag, lambda t: t.workspace_id)
        register(DocumentTag, lambda link: link.tag.workspace_id)

        pre_delete.connect(signals.forget_deleted_actor, sender=settings.AUTH_USER_MODEL, dispatch_uid="audit-user-pre-del")
        post_delete.connect(signals.remember_actor_again, sender=settings.AUTH_USER_MODEL, dispatch_uid="audit-user-del")
