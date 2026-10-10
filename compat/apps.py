from django.apps import AppConfig


class CompatConfig(AppConfig):
    """TEMPORARY app: remove during final integration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "compat"
    verbose_name = "Temporary compatibility models"

    def ready(self):
        from compat import signals

        signals.connect()
