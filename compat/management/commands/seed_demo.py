"""
TEMPORARY: seed standalone demo data for Postman. Lives in the compat app
because it creates Workspace/WorkspaceMember/Tag rows owned by teammates.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from compat.models import Tag, Workspace, WorkspaceMember
from documents import services

USERS = [("alice", "admin"), ("bob", "editor"), ("carol", "viewer"), ("dave", None)]
DEMO_PASSWORD = "collabdocs-demo-123"


class Command(BaseCommand):
    help = "Create demo users (admin/editor/viewer/outsider), a workspace, tags and one document."

    def handle(self, *args, **options):
        User = get_user_model()
        workspace, _ = Workspace.objects.get_or_create(name="Demo Workspace")
        tokens = {}
        for username, role in USERS:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            if role:
                WorkspaceMember.objects.update_or_create(workspace=workspace, user=user, defaults={"role": role})
            tokens[username] = (role or "not a member", Token.objects.get_or_create(user=user)[0].key)

        alice = User.objects.get(username="alice")
        if workspace.owner_id is None:
            workspace.owner = alice
            workspace.save(update_fields=["owner"])

        document = workspace.documents.filter(title="Project Plan").first()
        if document is None:
            document, _ = services.create_document(
                user=alice, workspace=workspace, title="Project Plan", content="First draft of the plan."
            )
        for name in ("planning", "backend"):
            Tag.objects.get_or_create(name=name)[0].documents.add(document)

        self.stdout.write(self.style.SUCCESS("Demo data ready.\n"))
        self.stdout.write(f"workspace_id = {workspace.pk}")
        self.stdout.write(f"document_id  = {document.pk}")
        self.stdout.write(f"password for all users = {DEMO_PASSWORD}\n")
        for username, (role, key) in tokens.items():
            self.stdout.write(f"{username:<6} ({role:<13}) token = {key}")
