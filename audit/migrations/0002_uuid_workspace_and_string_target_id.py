"""
Integrate AuditLog with UUID primary keys (Person A's Workspace, Person B's Document).

workspace_id: bigint -> uuid. PostgreSQL has no bigint -> uuid cast, so an AlterField would
fail even on an empty table; the column is dropped and re-added instead. No integer workspace
id ever existed in the combined project, so there is nothing meaningful to carry over.

target_id: bigint -> varchar(64). bigint -> varchar casts cleanly, so existing values survive.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="auditlog",
            name="audit_ws_created_idx",
        ),
        migrations.RemoveField(
            model_name="auditlog",
            name="workspace_id",
        ),
        migrations.AddField(
            model_name="auditlog",
            name="workspace_id",
            field=models.UUIDField(null=True),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["workspace_id", "-created_at"], name="audit_ws_created_idx"),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="target_id",
            field=models.CharField(max_length=64),
        ),
    ]
