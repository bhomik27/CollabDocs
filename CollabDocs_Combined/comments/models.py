"""
Comment data model.

A comment belongs to a document. A reply is a comment whose `parent` points at another
comment. Only ONE level of nesting is allowed (replies cannot have replies); the serializer
enforces that.
"""
from django.conf import settings
from django.db import models


class Comment(models.Model):
    document = models.ForeignKey("documents.Document", on_delete=models.CASCADE, related_name="comments")
    # SET_NULL: if a user account is deleted their comments stay (shown with author = null).
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    # Self-referencing FK = threading. Deleting a parent deletes its replies (CASCADE).
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["document", "created_at"])]  # the list endpoint's exact query

    def __str__(self):
        return f"Comment {self.pk} on document {self.document_id}"
