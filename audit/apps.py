from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"

    def ready(self):
        """Turn on auditing for Person C's models.

        Person A and Person B add the same one-liner for THEIR models in their own AppConfig.ready()
        (see INTEGRATION.md). Forgetting this step fails silently: nothing is logged, nothing errors.
        """
        from audit.registry import register
        from comments.models import Comment
        from tags.models import DocumentTag, Tag

        register(Comment, lambda c: c.document.workspace_id)
        register(Tag, lambda t: t.workspace_id)
        register(DocumentTag, lambda link: link.tag.workspace_id)
