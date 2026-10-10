from django.apps import AppConfig


class WorkspacesConfig(AppConfig):
    name = "workspaces"

    def ready(self):
        from audit.registry import register

        from .models import Workspace, WorkspaceMember

        register(Workspace, lambda w: w.pk)
        register(WorkspaceMember, lambda m: m.workspace_id)
