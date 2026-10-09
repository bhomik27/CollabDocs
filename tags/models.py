"""
Tag data model.

Tag          - a label that belongs to ONE workspace (name unique per workspace).
DocumentTag  - the join row "this tag is on this document". We define it ourselves instead of
               using ManyToManyField on Document so that Person B's Document model is never
               edited (fewer merge conflicts) and so tagging is auditable as its own event.
"""
from django.db import models


class Tag(models.Model):
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default="#808080")  # "#RRGGBB"

    class Meta:
        ordering = ["name"]
        constraints = [
            # The database itself guarantees no duplicate tag names inside a workspace.
            models.UniqueConstraint(fields=["workspace", "name"], name="unique_tag_name_per_workspace"),
        ]

    def __str__(self):
        return self.name


class DocumentTag(models.Model):
    document = models.ForeignKey("documents.Document", on_delete=models.CASCADE, related_name="document_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="document_tags")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "tag"], name="unique_tag_per_document"),
        ]

    def __str__(self):
        return f"{self.tag_id} on {self.document_id}"
