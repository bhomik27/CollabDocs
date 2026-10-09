from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = 'documents'

    def ready(self):
        from audit.registry import register

        from documents.models import Document

        # Versions are not registered: every version is created together with a Document
        # save, which is already audited (one row per save).
        register(Document, lambda doc: doc.workspace_id)
