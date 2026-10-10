"""Serializers for tags: validate input and shape output."""
from django.core.validators import RegexValidator
from rest_framework import serializers

from .models import DocumentTag, Tag

HEX_COLOR = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Color must look like #RRGGBB.")


class TagSerializer(serializers.ModelSerializer):
    """Read + write representation of a Tag.

    `workspace` is read-only: it comes from the URL, never from the client.
    `document_count` uses the value annotated by the view (1 query for the whole list);
    if absent (e.g. just-created tag) it falls back to a COUNT query.
    """

    color = serializers.CharField(max_length=7, required=False, validators=[HEX_COLOR])
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Tag
        fields = ["id", "workspace", "name", "color", "document_count"]
        read_only_fields = ["id", "workspace"]

    def get_document_count(self, obj):
        count = getattr(obj, "document_count", None)
        return obj.document_tags.count() if count is None else count

    def validate_name(self, value):
        """Reject a name already used in the same workspace (friendly 400 instead of a DB 500)."""
        value = value.strip()
        workspace_id = self.context["workspace"].pk if "workspace" in self.context else self.instance.workspace_id
        clash = Tag.objects.filter(workspace_id=workspace_id, name__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A tag with this name already exists in this workspace.")
        return value


class AttachTagSerializer(serializers.Serializer):
    """Body for POST /documents/{id}/tags/ : {"tag_id": 3}.

    The allowed tags are restricted to the document's own workspace, so a tag from another
    workspace is rejected with the same error as a tag that does not exist.
    """

    tag_id = serializers.PrimaryKeyRelatedField(source="tag", queryset=Tag.objects.none())

    def get_fields(self):
        fields = super().get_fields()
        document = self.context["document"]
        fields["tag_id"].queryset = Tag.objects.filter(workspace_id=document.workspace_id)
        return fields


class DocumentTagSerializer(serializers.ModelSerializer):
    """Output for attach: the link plus a compact view of the tag."""

    tag = TagSerializer(read_only=True)

    class Meta:
        model = DocumentTag
        fields = ["id", "document", "tag", "created_at"]
