# Adds the Tag <-> Document many-to-many over the existing DocumentTag table.
# State-only for the database: a ManyToManyField with an explicit `through` creates no table or column.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0001_initial"),
        ("tags", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tag",
            name="documents",
            field=models.ManyToManyField(blank=True, related_name="tags", through="tags.DocumentTag", to="documents.document"),
        ),
    ]
