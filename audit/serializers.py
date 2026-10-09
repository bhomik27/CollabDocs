from rest_framework import serializers

from core.utils import brief_user

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """Read-only output of an audit entry (there is no input serializer: the API never writes logs)."""

    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ["id", "workspace_id", "actor", "action", "target_type", "target_id", "changes", "created_at"]
        read_only_fields = fields

    def get_actor(self, obj):
        return brief_user(obj.actor)
