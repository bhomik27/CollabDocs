"""
`python manage.py check_integration` - verifies the contracts between Person A's, B's and C's apps.

It checks every assumption the comments/tags/audit and documents code makes about the rest of
the project and prints PASS / WARN / FAIL with the exact fix. Exit code is 1 if anything FAILs.
"""
import importlib
import inspect
import uuid

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models
from django.urls import NoReverseMatch, reverse

from audit.registry import registered_models
from core.access import ROLE_RANK

AUDIT_ID_MODELS = (("workspaces", "Workspace"), ("workspaces", "WorkspaceMember"), ("documents", "Document"))

_U = uuid.UUID(int=1)
URL_CHECKS = [
    ("document-comments", [_U]), ("comment-detail", [1]),
    ("workspace-tags", [_U]), ("tag-detail", [1]), ("document-tag-attach", [_U]), ("document-tag-detach", [_U, 1]),
    ("workspace-audit-logs", [_U]), ("audit-log-detail", [1]),
]


class Command(BaseCommand):
    help = "Verify the integration contracts between the users/workspaces, documents and comments/tags/audit apps."

    def handle(self, *args, **options):
        self.failed = False
        self.check_models()
        self.check_roles()
        self.check_tags_relation()
        self.check_middleware()
        self.check_drf_settings()
        self.check_audit_registrations()
        self.check_urls()
        self.stdout.write("")
        if self.failed:
            self.stdout.write(self.style.ERROR("Integration check FAILED - fix the FAIL lines above."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Integration check passed (review any WARN lines)."))

    # ---- output helpers ----
    def ok(self, msg):
        self.stdout.write(self.style.SUCCESS("PASS ") + msg)

    def warn(self, msg):
        self.stdout.write(self.style.WARNING("WARN ") + msg)

    def fail(self, msg):
        self.failed = True
        self.stdout.write(self.style.ERROR("FAIL ") + msg)

    # ---- checks ----
    def check_models(self):
        audit_log = apps.get_model("audit", "AuditLog")
        if isinstance(audit_log._meta.get_field("workspace_id"), models.UUIDField):
            self.ok("AuditLog.workspace_id is a UUIDField")
        else:
            self.fail("AuditLog.workspace_id must be a UUIDField (workspaces use UUID primary keys).")
        if isinstance(audit_log._meta.get_field("target_id"), models.CharField):
            self.ok("AuditLog.target_id is a CharField (holds UUID and integer primary keys)")
        else:
            self.fail("AuditLog.target_id must be a CharField: audited models mix UUID and integer primary keys.")

        workspace = apps.get_model("workspaces", "Workspace")
        if isinstance(workspace._meta.pk, models.UUIDField):
            self.ok("workspaces.Workspace has a UUID primary key (matches AuditLog.workspace_id)")
        else:
            self.fail("workspaces.Workspace primary key is not a UUID; AuditLog.workspace_id and the URL converters assume UUIDs.")

        for label, name in AUDIT_ID_MODELS:
            try:
                apps.get_model(label, name)
                self.ok(f"{label}.{name} exists")
            except LookupError:
                self.fail(f"{label}.{name} not found (core/access.py and documents/integration.py import it).")
        try:
            member = apps.get_model("workspaces", "WorkspaceMember")
            for field in ("workspace", "user", "role"):
                member._meta.get_field(field)
            self.ok("WorkspaceMember has fields workspace, user, role")
        except Exception:
            self.fail("WorkspaceMember must have fields named 'workspace', 'user' and 'role' - or adapt core/access.py.")
        try:
            document = apps.get_model("documents", "Document")
            if document._meta.get_field("workspace").many_to_one:
                self.ok("Document has a workspace ForeignKey")
        except Exception:
            self.fail("Document must have a ForeignKey named 'workspace' (comments, tags and audit resolve workspace through it).")

    def check_roles(self):
        role_field = apps.get_model("workspaces", "WorkspaceMember")._meta.get_field("role")
        theirs = {value for value, _ in role_field.choices or []}
        missing = set(ROLE_RANK) - theirs
        extra = theirs - set(ROLE_RANK)
        if missing:
            self.fail(f"core/access.py ROLE_RANK uses role(s) {sorted(missing)} that WorkspaceMember.Role does not define.")
        else:
            self.ok(f"WorkspaceMember.role values match ROLE_RANK ({', '.join(ROLE_RANK)})")
        if extra:
            self.warn(f"WorkspaceMember.role has extra values {sorted(extra)} not in ROLE_RANK - they rank as 0 (no permissions).")

    def check_tags_relation(self):
        relation = getattr(settings, "COLLABDOCS_DOCUMENT_TAGS_RELATION", None)
        if not relation:
            self.warn("COLLABDOCS_DOCUMENT_TAGS_RELATION is unset: document tag filtering/prefetching is disabled.")
            return
        try:
            related = apps.get_model("documents", "Document")._meta.get_field(relation).related_model
            related._meta.get_field("name")
            self.ok(f"Document.{relation} reaches {related._meta.label}.name (tag filter and serializer work)")
        except Exception:
            self.fail(f"Document.{relation} must be a relation to a model with a 'name' field (tags.Tag via Tag.documents).")

    def check_middleware(self):
        for path in settings.MIDDLEWARE:
            try:
                module_path, class_name = path.rsplit(".", 1)
                middleware = getattr(importlib.import_module(module_path), class_name)
                if "set_request" in inspect.getsource(middleware):
                    self.ok(f"{path} publishes the request via core.context.set_request (audit actor will be recorded)")
                    return
            except Exception:
                continue
        self.fail("No middleware calls core.context.set_request(). Audit entries would have actor = null. "
                  "Add core.middleware.AuditContextMiddleware to MIDDLEWARE.")

    def check_drf_settings(self):
        rest = getattr(settings, "REST_FRAMEWORK", {})
        if rest.get("DEFAULT_PAGINATION_CLASS"):
            self.ok("DRF pagination is configured")
        else:
            self.warn("REST_FRAMEWORK has no DEFAULT_PAGINATION_CLASS: comment/tag/audit/document lists would return "
                      "bare lists instead of {count, next, previous, results}.")
        perms = rest.get("DEFAULT_PERMISSION_CLASSES", [])
        if any("IsAuthenticated" in p for p in perms):
            self.ok("DRF default permission is IsAuthenticated")
        else:
            self.warn("DEFAULT_PERMISSION_CLASSES does not include IsAuthenticated; anonymous users would reach the views "
                      "(they would still get 404 because they are not members).")

    def check_audit_registrations(self):
        registered = {m._meta.label for m in registered_models()}
        for label in ("comments.Comment", "tags.Tag", "tags.DocumentTag",
                      "documents.Document", "workspaces.Workspace", "workspaces.WorkspaceMember"):
            if label in registered:
                self.ok(f"{label} is audited")
            else:
                self.fail(f"{label} is NOT registered with audit (register(...) in its app's AppConfig.ready()).")

    def check_urls(self):
        bad = []
        for name, args in URL_CHECKS:
            try:
                reverse(name, args=args)
            except NoReverseMatch:
                bad.append(name)
        if bad:
            self.fail(f"URL names not resolvable: {bad}. Add path('api/', include('<app>.urls')) to the root urls.py.")
        else:
            self.ok("All comment, tag and audit endpoints are routed (8 URL patterns)")
