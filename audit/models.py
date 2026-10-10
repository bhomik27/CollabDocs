"""
AuditLog: an append-only record of "who did what to which object, when".

Rows are written ONLY by signal handlers (audit/signals.py), never by views, and the API
exposes them read-only. `save()` refuses to modify an existing row, enforcing append-only
in code as well as in the API surface.

`workspace_id` is a plain UUID, not a ForeignKey, on purpose: an audit trail must outlive
the things it describes, and an FK would make deleting a workspace delete or block its history.
`target_id` is a string because audited models mix UUID primary keys (Workspace, Document)
and integer primary keys (Comment, Tag, DocumentTag).
"""
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create"
        UPDATE = "update"
        DELETE = "delete"

    # No single-column index: the composite index in Meta (workspace_id, -created_at) covers it.
    workspace_id = models.UUIDField(null=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=10, choices=Action.choices)
    target_type = models.CharField(max_length=50)      # model name, e.g. "comment", "tag", "documenttag"
    target_id = models.CharField(max_length=64)        # str(pk) of the changed object
    changes = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            # The list endpoint's exact query: one workspace, newest first.
            models.Index(fields=["workspace_id", "-created_at"], name="audit_ws_created_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("AuditLog entries are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.action} {self.target_type}#{self.target_id}"
