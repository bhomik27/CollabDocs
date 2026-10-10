# CollabDocs integration notes

This project combines three independently developed implementations:
- `users/`, `workspaces/`: Person A
- `documents/`: Person B
- `comments/`, `tags/`, `audit/`: Person C
- `config/`: shared settings and API routing
- `core/`: shared helpers (`access.py` authorization policy, `context.py` + `middleware.py` request context, test fixture)

`python manage.py check_integration` verifies every contract below and exits non-zero on a mismatch.

## Contracts (resolved)

| Topic | Decision | Where |
| --- | --- | --- |
| Primary keys | User, Workspace, WorkspaceMember, Document, DocumentVersion: UUID. Comment, Tag, DocumentTag, AuditLog: bigint. | models |
| URL converters | Workspace and document ids in C's routes use `<uuid:...>`; comment, tag and audit-log ids stay `<int:...>`. | `comments/urls.py`, `tags/urls.py`, `audit/urls.py` |
| Membership | `workspaces.WorkspaceMember` (workspace, user, role) is the single source of truth for authorization. | `core/access.py`, `core/permissions.py`, `documents/integration.py` |
| Roles | `viewer < editor < admin`. There is no `owner` role: `Workspace.owner` is recorded on the workspace, and the creator receives an `admin` membership in the same transaction, so an owner is authorized as an admin. | `core/access.py` |
| Tags on documents | `tags.Tag.documents` is a many-to-many **through** the existing `tags.DocumentTag` table (`related_name="tags"`), so `Document.tags` works for B's filter, prefetch and serializer without editing `Document`. | `tags/models.py`, `config/settings.py` (`COLLABDOCS_DOCUMENT_TAGS_RELATION = "tags"`) |
| Audit storage | `AuditLog.workspace_id` is a UUID; `target_id` is a string (`str(pk)`) because audited models mix UUID and integer keys. | `audit/models.py` |
| Audited models | Comment, Tag, DocumentTag (`audit/apps.py`); Workspace, WorkspaceMember (`workspaces/apps.py`); Document (`documents/apps.py`). DocumentVersion is not audited: each version is created together with an audited Document save. One registry, `dispatch_uid`-deduplicated, so no duplicate rows. | `AppConfig.ready()` |
| Audit actor | The authenticated user making the request, published by `core.middleware.AuditContextMiddleware`. ORM changes outside a request have `actor = null`. | `config/settings.py` `MIDDLEWARE` |
| Audit on delete | Final values are captured in `pre_delete` (deferred fields loaded while the row exists). Rows written while a user's own account is being deleted (cascade through `Workspace.owner`) get `actor = null`, otherwise the deferred FK check would fail at commit. | `audit/signals.py` |
| Pagination | Global `PageNumberPagination`. Person A's `/api/users/` and `/api/workspaces/` keep returning plain arrays (`pagination_class = None`), as in A's original API. | `users/views.py`, `workspaces/views.py` |
| Login | `/api/users/` (register), `/api/users/login/` and `/api/auth/token/` all issue DRF tokens. | `users/views.py`, `config/urls.py` |
| Errors | One `EXCEPTION_HANDLER`: `documents.exceptions.api_exception_handler` (IntegrityError -> 409, safe 500 JSON, `code` field). Malformed UUID/date query parameters return 400. | `config/settings.py`, `core/utils.parse_query_value` |

## Migrations

- `documents/0001_initial` originally depended on Person B's temporary `compat` app, which is not part of this project. Its dependency and the `Document.workspace` FK target were changed to `workspaces.0001_initial` / `workspaces.workspace` (it could never have been applied: the migration graph did not load).
- `audit/0002_uuid_workspace_and_string_target_id`: `workspace_id` is dropped and re-added as UUID (PostgreSQL cannot cast bigint to uuid); `target_id` is altered to varchar.
- `tags/0002_tag_documents`: adds `Tag.documents` (state only; no table or column).

Order: `users.0001 -> workspaces.0001 -> documents.0001 -> comments.0001, tags.0001 -> tags.0002`; `audit.0001 -> audit.0002`.

## PostgreSQL

Person B's concurrency guarantees rely on `select_for_update()` row locks; `documents/tests/test_concurrency.py` runs only on PostgreSQL and is skipped on SQLite.
