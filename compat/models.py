"""
TEMPORARY compatibility models -- NOT part of Person B's deliverable.

These stand in for models owned by teammates so the Documents app can be
developed and tested on its own:

    Workspace, WorkspaceMember  -> Person A (workspaces / membership)
    Tag, Comment, AuditLog      -> Person C (collaboration / auditing)

Only the fields the Documents app relies on are modelled. During final
integration this whole app is removed and ``documents/integration.py`` is
pointed at the real models. See README "Final integration".
"""

import uuid

from django.conf import settings
from django.db import models


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class WorkspaceMember(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        EDITOR = "editor", "Editor"
        VIEWER = "viewer", "Viewer"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VIEWER)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="compat_unique_workspace_member"),
        ]

    def __str__(self):
        return f"{self.user} in {self.workspace} ({self.role})"


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    # Contract relied on by documents: reverse accessor ``Document.tags``.
    documents = models.ManyToManyField("documents.Document", related_name="tags", blank=True)

    def __str__(self):
        return self.name


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Contract relied on by documents: reverse accessor ``Document.comments``.
    document = models.ForeignKey("documents.Document", on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=20)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp", "id"]
