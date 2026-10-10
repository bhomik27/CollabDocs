import uuid

from django.conf import settings
from django.db import models
from django.db.models import OuterRef, Q, Subquery

from documents import integration


class DocumentQuerySet(models.QuerySet):
    def for_user(self, user):
        """
        Documents in workspaces the user belongs to, annotated with the user's
        role in that workspace (``user_role``) so permission checks need no
        extra query. Documents elsewhere are simply absent, which turns
        unauthorized access into a 404 instead of leaking existence.
        """
        memberships = integration.memberships_for(user)
        return self.filter(workspace_id__in=memberships.values_list("workspace_id", flat=True)).annotate(
            user_role=Subquery(memberships.filter(workspace_id=OuterRef("workspace_id")).values("role")[:1])
        )


class Document(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    workspace = models.ForeignKey(integration.WORKSPACE_MODEL, on_delete=models.CASCADE, related_name="documents")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_documents"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["workspace", "status"], name="document_workspace_status_idx"),
            models.Index(fields=["updated_at"], name="document_updated_at_idx"),
        ]

    def __str__(self):
        return self.title


class DocumentVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    content = models.TextField(blank=True)
    version_number = models.PositiveIntegerField()
    saved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="saved_document_versions"
    )
    saved_at = models.DateTimeField(auto_now_add=True)
    # Set when this version was produced by restoring an older one.
    restored_from = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["document", "version_number"]
        constraints = [
            # Last line of defence against duplicate numbers from concurrent writers.
            models.UniqueConstraint(fields=["document", "version_number"], name="unique_document_version_number"),
            models.CheckConstraint(condition=Q(version_number__gte=1), name="document_version_number_gte_1"),
        ]

    def __str__(self):
        return f"{self.document_id} v{self.version_number}"
