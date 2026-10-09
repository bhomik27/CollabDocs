"""
`python manage.py check_integration` - run this right after merging A, B and C.

It checks every assumption Person C's code makes about the rest of the project and prints
PASS / WARN / FAIL with the exact fix, so a mismatch is found in seconds instead of by
reading a stack trace. Exit code is 1 if anything FAILs.
"""
import importlib
import inspect

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models
from django.urls import NoReverseMatch, reverse

from audit.registry import registered_models
from core.access import ROLE_RANK

INTEGER_PK = (models.AutoField, models.BigAutoField, models.SmallAutoField, models.IntegerField)

URL_CHECKS = [
    ("document-comments", [1]), ("comment-detail", [1]),
    ("workspace-tags", [1]), ("tag-detail", [1]), ("document-tag-attach", [1]), ("document-tag-detach", [1, 1]),
    ("workspace-audit-logs", [1]), ("audit-log-detail", [1]),
]


class Command(BaseCommand):
    help = "Verify Person C's assumptions about Person A's and Person B's code."

    def handle(self, *args, **options):
        self.failed = False
        self.check_models()
        self.check_roles()
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
        for label, name in (("workspaces", "Workspace"), ("workspaces", "Membership"), ("documents", "Document")):
            try:
                model = apps.get_model(label, name)
            except LookupError:
                self.fail(f"{label}.{name} not found. Person {'B' if label == 'documents' else 'A'}'s app must be in "
                          f"INSTALLED_APPS with a model named {name} (else edit the imports in core/access.py).")
                continue
            self.ok(f"{label}.{name} exists")
            if not isinstance(model._meta.pk, INTEGER_PK):
                self.fail(f"{label}.{name} has a non-integer primary key ({type(model._meta.pk).__name__}). "
                          "AuditLog and the URL patterns assume integer ids (see INTEGRATION.md, 'Integer ids').")
        User = settings.AUTH_USER_MODEL
        user_model = apps.get_model(User)
        if not isinstance(user_model._meta.pk, INTEGER_PK):
            self.fail(f"{User} has a non-integer primary key; brief_user/AuditLog.actor assume integer-compatible ids.")
        try:
            membership = apps.get_model("workspaces", "Membership")
            for field in ("workspace", "user", "role"):
                membership._meta.get_field(field)
            self.ok("Membership has fields workspace, user, role")
        except Exception:
            self.fail("Membership must have fields named 'workspace', 'user' and 'role' - or adapt core/access.py.")
        try:
            document = apps.get_model("documents", "Document")
            if document._meta.get_field("workspace").many_to_one:
                self.ok("Document has a workspace ForeignKey")
        except Exception:
            self.fail("Document must have a ForeignKey named 'workspace' (comments, tags and audit resolve workspace through it).")

    def check_roles(self):
        try:
            role_field = apps.get_model("workspaces", "Membership")._meta.get_field("role")
        except Exception:
            return
        if role_field.is_relation:
            self.warn("Membership.role is a relation, not a string. Adapt get_role()/has_role() in core/access.py.")
            return
        if not role_field.choices:
            self.warn("Membership.role has no choices, so role names cannot be verified. "
                      f"Person C expects: {', '.join(ROLE_RANK)} (edit ROLE_RANK in core/access.py if A's names differ).")
            return
        theirs = {value for value, _ in role_field.choices}
        missing = set(ROLE_RANK) - theirs
        extra = theirs - set(ROLE_RANK)
        if missing:
            self.fail(f"Membership.role has no value(s) {sorted(missing)} that core/access.py ROLE_RANK uses. "
                      "Map A's role names in ROLE_RANK.")
        else:
            self.ok("Membership.role values cover viewer/editor/admin/owner")
        if extra:
            self.warn(f"Membership.role has extra values {sorted(extra)} not in ROLE_RANK - they rank as 0 (no permissions).")

    def check_middleware(self):
        for path in settings.MIDDLEWARE:
            try:
                module = importlib.import_module(path.rsplit(".", 1)[0])
                if "set_request" in inspect.getsource(module):
                    self.ok(f"{path} publishes the request via core.context.set_request (audit actor will be recorded)")
                    return
            except Exception:
                continue
        self.fail("No middleware calls core.context.set_request(). Audit entries would have actor = null. "
                  "Add the 2 lines to Person A's middleware (INTEGRATION.md section 4.3).")

    def check_drf_settings(self):
        rest = getattr(settings, "REST_FRAMEWORK", {})
        if rest.get("DEFAULT_PAGINATION_CLASS"):
            self.ok("DRF pagination is configured")
        else:
            self.warn("REST_FRAMEWORK has no DEFAULT_PAGINATION_CLASS: list endpoints will return bare lists instead of "
                      "{count, next, previous, results}. Postman tests written for Person C assume pagination.")
        perms = rest.get("DEFAULT_PERMISSION_CLASSES", [])
        if any("IsAuthenticated" in p for p in perms):
            self.ok("DRF default permission is IsAuthenticated")
        else:
            self.warn("DEFAULT_PERMISSION_CLASSES does not include IsAuthenticated; anonymous users would reach C's views "
                      "(they would still get 404 because they are not members).")

    def check_audit_registrations(self):
        registered = {m._meta.label for m in registered_models()}
        for label in ("comments.Comment", "tags.Tag", "tags.DocumentTag"):
            (self.ok if label in registered else self.fail)(f"{label} is audited" if label in registered
                                                           else f"{label} is NOT registered with audit (audit/apps.py).")
        for label, owner in (("documents.Document", "B"), ("workspaces.Workspace", "A"), ("workspaces.Membership", "A")):
            if label not in registered:
                self.warn(f"{label} is not audited yet. Person {owner}: add register(...) in your AppConfig.ready() "
                          "(INTEGRATION.md section 4.4).")
            else:
                self.ok(f"{label} is audited")

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
            self.ok("All 14 of Person C's endpoints are routed (8 URL patterns)")
