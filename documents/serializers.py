from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from documents import integration, services
from documents.models import Document, DocumentVersion

# Fields the server owns. Sending them is rejected rather than silently
# ignored so a client cannot believe it set a creator or version number.
SERVER_CONTROLLED_FIELDS = ("id", "created_by", "created_at", "updated_at", "version_number", "version_count", "saved_by")


class UserSummarySerializer(serializers.Serializer):
    id = serializers.CharField(source="pk", read_only=True)
    username = serializers.CharField(source="get_username", read_only=True)


STATUS_ERROR_MESSAGES = {
    "invalid_choice": f'"{{input}}" is not a valid status. Choose one of: {", ".join(Document.Status.values)}.'
}


class DocumentSerializer(serializers.ModelSerializer):
    workspace = serializers.PrimaryKeyRelatedField(
        queryset=integration.get_workspace_model().objects.none(),
        pk_field=serializers.UUIDField(),
        error_messages={"does_not_exist": "Workspace not found or you are not a member of it."},
    )
    status = serializers.ChoiceField(choices=Document.Status.choices, required=False, error_messages=STATUS_ERROR_MESSAGES)
    created_by = UserSummarySerializer(read_only=True)
    tags = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id", "title", "content", "workspace", "status", "tags",
            "created_by", "version_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"content": {"required": True, "allow_blank": True, "trim_whitespace": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if "workspace" in self.fields and request is not None:
            # Only workspaces the caller belongs to are valid choices.
            self.fields["workspace"].queryset = integration.get_workspace_model().objects.filter(
                pk__in=integration.accessible_workspace_ids(request.user)
            )
        if self.instance is not None and "workspace" in self.fields:
            # Workspace is fixed after creation; PUT may omit it.
            self.fields["workspace"].required = False
        if "tags" in self.fields:
            if integration.DOCUMENT_TAGS_RELATION:
                self.fields["tags"].source = integration.DOCUMENT_TAGS_RELATION
            else:
                self.fields.pop("tags")

    def get_version_count(self, obj):
        count = getattr(obj, "version_count", None)
        return count if count is not None else obj.versions.count()

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            spoofed = [name for name in SERVER_CONTROLLED_FIELDS if name in data]
            if spoofed:
                raise serializers.ValidationError({name: ["This field is set by the server and cannot be provided."] for name in spoofed})
        return super().to_internal_value(data)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title cannot be blank.")
        return value

    def validate_workspace(self, workspace):
        if self.instance is not None and workspace.pk != self.instance.workspace_id:
            raise serializers.ValidationError("A document cannot be moved to another workspace.")
        if self.instance is None:
            role = integration.get_role(self.context["request"].user, workspace.pk)
            if role not in integration.WRITE_ROLES:
                raise PermissionDenied("Only workspace admins and editors can create documents.")
        return workspace

    def create(self, validated_data):
        document, _ = services.create_document(user=self.context["request"].user, **validated_data)
        return document

    def update(self, instance, validated_data):
        validated_data.pop("workspace", None)
        document, _ = services.update_document(instance.pk, user=self.context["request"].user, **validated_data)
        return document


class DocumentListSerializer(DocumentSerializer):
    """List rows omit ``content`` so listing never loads full document bodies."""

    class Meta(DocumentSerializer.Meta):
        fields = [f for f in DocumentSerializer.Meta.fields if f != "content"]


class DocumentVersionSerializer(serializers.ModelSerializer):
    saved_by = UserSummarySerializer(read_only=True)
    restored_from_version = serializers.IntegerField(source="restored_from.version_number", read_only=True, default=None)

    class Meta:
        model = DocumentVersion
        fields = ["id", "document", "version_number", "content", "saved_by", "saved_at", "restored_from", "restored_from_version"]
        read_only_fields = fields


class DocumentVersionListSerializer(DocumentVersionSerializer):
    """Version history rows omit the content snapshot; fetch a version to see it."""

    class Meta(DocumentVersionSerializer.Meta):
        fields = ["id", "document", "version_number", "saved_by", "saved_at", "restored_from"]
        read_only_fields = fields


class RestoreResultSerializer(serializers.Serializer):
    document = DocumentSerializer(read_only=True)
    version = DocumentVersionSerializer(read_only=True)
    restored_from_version = serializers.IntegerField(read_only=True)


class DocumentStatsSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    version_count = serializers.IntegerField()
    latest_version_number = serializers.IntegerField(allow_null=True)
    last_saved_at = serializers.DateTimeField(allow_null=True)
    comment_count = serializers.IntegerField()
    contributor_count = serializers.IntegerField(
        help_text="Distinct users who saved a version or wrote a comment on the document."
    )


# --------------------------------------------------------------------------
# Query-parameter validation for GET /api/documents/
# --------------------------------------------------------------------------

class DateOrDateTimeField(serializers.Field):
    """
    Accepts an ISO date (``2026-10-01``) or datetime (``2026-10-01T09:30:00Z``).
    A bare date means the start of that day, or its end when ``end_of_day``.
    Naive datetimes are interpreted in the project time zone.
    """

    default_error_messages = {"invalid": "Use an ISO 8601 date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM[:SS][TZ])."}

    def __init__(self, *, end_of_day=False, **kwargs):
        self.end_of_day = end_of_day
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = str(data).strip()
        try:
            parsed = parse_datetime(value)
            if parsed is None:
                day = parse_date(value)
                if day is None:
                    self.fail("invalid")
                parsed = datetime.combine(day, time.max if self.end_of_day else time.min)
        except ValueError:  # well-formed but impossible, e.g. 2026-02-30
            self.fail("invalid")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed)
        return parsed


class DocumentFilterSerializer(serializers.Serializer):
    workspace = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(choices=Document.Status.choices, required=False, error_messages=STATUS_ERROR_MESSAGES)
    status_in = serializers.CharField(required=False, help_text="Comma-separated statuses, e.g. draft,published")
    tag = serializers.CharField(required=False, max_length=100)
    search = serializers.CharField(required=False, max_length=255)
    created_by = serializers.CharField(required=False)
    updated_after = DateOrDateTimeField(required=False)
    updated_before = DateOrDateTimeField(required=False, end_of_day=True)

    def validate_status_in(self, value):
        statuses = [s.strip() for s in value.split(",") if s.strip()]
        if not statuses:
            raise serializers.ValidationError("Provide at least one status.")
        invalid = sorted(set(statuses) - set(Document.Status.values))
        if invalid:
            raise serializers.ValidationError(
                f"Invalid status value(s): {', '.join(invalid)}. Choose from: {', '.join(Document.Status.values)}."
            )
        return statuses

    def validate_created_by(self, value):
        try:
            return get_user_model()._meta.pk.to_python(value)
        except DjangoValidationError:
            raise serializers.ValidationError("Not a valid user id.")

    def validate(self, attrs):
        after, before = attrs.get("updated_after"), attrs.get("updated_before")
        if after and before and after > before:
            raise serializers.ValidationError({"updated_before": "Must be later than or equal to updated_after."})
        return attrs
