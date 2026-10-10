"""
Test fixtures. This is the only test module that constructs teammates' models
(Workspace, WorkspaceMember, Tag, Comment, AuditLog), using the integrated
models' required fields.
"""

from itertools import count

from django.apps import apps
from django.contrib.auth import get_user_model

from documents import integration, services

_seq = count(1)


def make_user(username=None):
    username = username or f"user{next(_seq)}"
    # User.email is unique, so every user needs its own address.
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="test-pass-123"
    )


def make_workspace(name=None, owner=None):
    """A workspace with a dedicated owner. Membership is added explicitly with add_member()."""
    owner = owner or make_user()
    return integration.get_workspace_model().objects.create(name=name or f"Workspace {next(_seq)}", owner=owner)


def add_member(workspace, user, role):
    return integration.get_workspace_member_model().objects.create(workspace=workspace, user=user, role=role)


def make_document(workspace, user, title="Doc", content="v1 content", **extra):
    document, _ = services.create_document(user=user, workspace=workspace, title=title, content=content, **extra)
    return document


def tag_document(document, name):
    tag_model = document._meta.get_field(integration.DOCUMENT_TAGS_RELATION).related_model
    tag, _ = tag_model.objects.get_or_create(workspace_id=document.workspace_id, name=name)
    getattr(document, integration.DOCUMENT_TAGS_RELATION).add(tag)
    return tag


def add_comment(document, author, body="Nice"):
    return integration.get_comment_model().objects.create(document=document, author=author, body=body)


def audit_log_model():
    """Person C's AuditLog."""
    return apps.get_model("audit", "AuditLog")
