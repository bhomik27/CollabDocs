"""Serializers for comments. Three shapes: output, create-input, edit-input."""
from rest_framework import serializers

from core.utils import brief_user

from .models import Comment


class ReplySerializer(serializers.ModelSerializer):
    """A comment as shown inside its parent's `replies` list (no further nesting)."""

    author = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "author", "body", "parent", "created_at", "updated_at"]

    def get_author(self, obj):
        return brief_user(obj.author)


class CommentSerializer(ReplySerializer):
    """Full output shape: a comment plus its replies.

    `obj.replies.all()` reads the cache filled by the view's prefetch_related, so serializing
    N comments costs a constant number of queries.
    """

    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "document", "author", "body", "parent", "replies", "created_at", "updated_at"]

    def get_replies(self, obj):
        return ReplySerializer(obj.replies.all(), many=True, context=self.context).data


class CommentWriteSerializer(serializers.ModelSerializer):
    """Input for creating a comment. The client may send only `body` and optional `parent`.

    `author` and `document` are NOT accepted from the client; the view sets them from the
    logged-in user and the URL.
    """

    body = serializers.CharField(max_length=5000)

    class Meta:
        model = Comment
        fields = ["body", "parent"]

    def get_fields(self):
        """Limit `parent` to top-level comments on THIS document.

        One filter enforces three rules: parent must exist, must be on the same document,
        and must not itself be a reply. Anything else gets the standard 'Invalid pk' 400.
        """
        fields = super().get_fields()
        document = self.context.get("document")
        if document is not None:
            fields["parent"].queryset = Comment.objects.filter(document=document, parent__isnull=True)
        return fields


class CommentEditSerializer(serializers.ModelSerializer):
    """Input for editing: only the body can change (not parent, author or document)."""

    body = serializers.CharField(max_length=5000)

    class Meta:
        model = Comment
        fields = ["body"]
