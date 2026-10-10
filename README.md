# CollabDocs

API-only Django REST Framework backend for a simplified Notion / Google Docs:
users, workspaces with roles, documents with version history, comments, tags
and an audit log. It combines three implementations; see
[INTEGRATION_NOTES.md](INTEGRATION_NOTES.md) for the contracts between them.

| App | Owner | Responsibility |
| --- | --- | --- |
| `users/` | Person A | custom `User` (UUID), register / login / me |
| `workspaces/` | Person A | `Workspace` (owner), `WorkspaceMember` roles admin / editor / viewer |
| `documents/` | Person B | `Document`, `DocumentVersion`, transactional versioning, restore, stats |
| `comments/` | Person C | threaded comments on documents |
| `tags/` | Person C | per-workspace tags, attach / detach to documents |
| `audit/` | Person C | append-only `AuditLog` written by signals |
| `core/` | shared | authorization policy (`access.py`), request context + middleware, test fixture |
| `config/` | shared | settings (env-driven), root URLs |

Stack: Python 3.12+ (developed on 3.14), Django 6.0, DRF 3.18, PostgreSQL (psycopg 3).

**Demo video:** <PASTE LOOM / GOOGLE DRIVE LINK HERE>

**Postman collection:** [`CollabDocs.postman_collection.json`](CollabDocs.postman_collection.json) (repository root)

### Endpoints (all under `/api/`)

| Area | Endpoints |
| --- | --- |
| Auth / users | `POST users/` (register, returns token), `POST users/login/`, `GET users/me/`, `GET/PATCH/DELETE users/{uuid}/`, `POST auth/token/` |
| Workspaces | `GET/POST workspaces/`, `GET/PUT/PATCH/DELETE workspaces/{uuid}/`, `GET/POST workspaces/{uuid}/members/`, `GET workspaces/{uuid}/stats/` |
| Documents | see section 6 below (`documents/`, versions, restore, stats) |
| Comments | `GET/POST documents/{uuid}/comments/`, `GET/PATCH/DELETE comments/{id}/` |
| Tags | `GET/POST workspaces/{uuid}/tags/`, `GET/PATCH/DELETE tags/{id}/`, `POST documents/{uuid}/tags/`, `DELETE documents/{uuid}/tags/{id}/` |
| Audit | `GET workspaces/{uuid}/audit-logs/` (admins), `GET audit-logs/{id}/` |

The sections below document setup and, in detail, the documents & versions API.

---

## 1. Installation

Requires Python 3.12 or newer (Django 6.0). Clone the repository and run all
commands from the project root (the folder containing `manage.py`):

```bash
git clone https://github.com/bhomik27/CollabDocs.git
cd CollabDocs
```

```powershell
# Windows PowerShell
python -m venv venv                      # first time only
.\venv\Scripts\Activate.ps1             # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
```

```bash
# Git Bash / macOS / Linux
python -m venv venv                      # first time only
source venv/Scripts/activate             # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

See [API_TESTING.md](API_TESTING.md) for a step-by-step manual API test.

## 2. Environment configuration

```bash
cp .env.example .env      # then edit .env; it is git-ignored
```

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | required when `DJANGO_DEBUG=false` |
| `DJANGO_DEBUG` | `true` for local development |
| `DJANGO_ALLOWED_HOSTS` | comma-separated |
| `POSTGRES_DB / _USER / _PASSWORD / _HOST / _PORT` | PostgreSQL connection |
| `POSTGRES_CONN_MAX_AGE` | persistent connection lifetime in seconds |
| `USE_SQLITE` | `true` only on a machine without PostgreSQL (see the testing notes) |
| `DOCUMENTS_LOG_LEVEL` | log level for the documents app (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## 3. Create the PostgreSQL database

```sql
-- psql -U postgres
CREATE USER collabdocs WITH PASSWORD 'change-me';
CREATE DATABASE collabdocs OWNER collabdocs;
ALTER USER collabdocs CREATEDB;   -- lets the test runner create test_collabdocs
```

## 4. Apply migrations, check, run

All migrations are committed. Apply them to the configured database:

```bash
python manage.py migrate
python manage.py check_integration   # verifies the cross-app contracts
python manage.py createsuperuser     # optional, for /admin/ (asks for an email)
python manage.py runserver
```

Register users with `POST /api/users/` (the response contains a token), create
a workspace with `POST /api/workspaces/`, and add members with
`POST /api/workspaces/{id}/members/`.

## 5. Tests

```bash
python manage.py test                       # all apps, against PostgreSQL (recommended)
USE_SQLITE=true python manage.py test       # no PostgreSQL available (concurrency tests skipped)
```

* 111 tests across all apps. The documents app covers CRUD, versioning,
  restore, filters, permissions, error codes, rollback, the audit-signal
  contract, query counts, and concurrency.
* `documents/tests/test_concurrency.py` (4 tests) runs **only on PostgreSQL**.
  SQLite ignores `select_for_update()`, so it cannot prove anything about
  row locking, and those tests are skipped there.
* The concurrency tests were checked by deliberately removing the
  `select_for_update()`: three of the four then fail (duplicate version numbers
  and a lost update). They detect the bug they are meant to catch.

---

## 6. API

All endpoints require `Authorization: Token <token>` (session auth also
works). Errors return JSON: `{"detail": "...", "code": "..."}` or field-level
`{"field": ["message"]}`.

| Method | URL | Role | Success |
| --- | --- | --- | --- |
| POST | `/api/documents/` | admin, editor | 201 + version 1 |
| GET | `/api/documents/` | any member | 200 (paginated, filtered) |
| GET | `/api/documents/{id}/` | any member | 200 |
| PUT | `/api/documents/{id}/` | admin, editor | 200 + new version |
| PATCH | `/api/documents/{id}/` | admin, editor | 200 + new version |
| DELETE | `/api/documents/{id}/` | admin, or the editor who created it | 204 |
| GET | `/api/documents/{id}/versions/` | any member | 200, ascending |
| GET | `/api/documents/{id}/versions/{version_id}/` | any member | 200 |
| POST | `/api/documents/{id}/versions/{version_id}/restore/` | admin, editor | 201 + new version |
| GET | `/api/documents/{id}/stats/` | any member | 200 |
| POST | `/api/auth/token/` | — | token login (same tokens as `/api/users/login/`) |

CRUD comes from a `ModelViewSet`. Versions, version detail, restore and stats
are `@action`s on the same viewset.

### Status codes

| Code | When |
| --- | --- |
| 400 | invalid body or query parameter (field-level messages); attempting to set server-controlled fields (`id`, `created_by`, `version_number`, …); moving a document to another workspace |
| 401 | missing or invalid token |
| 403 | a member whose role does not allow the action (for example, a viewer editing) |
| 404 | missing or malformed document/version id, a version that belongs to another document, or **any document in a workspace you are not a member of** (concealment) |
| 409 | version-number conflict / `IntegrityError`; the transaction is rolled back |
| 500 | unexpected error: `{"detail": "An unexpected error occurred.", "code": "server_error"}`; never a traceback |

### Sample requests

```bash
TOKEN=...   # from POST /api/users/login/
curl -X POST http://127.0.0.1:8000/api/documents/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"title": "API Design", "content": "Draft 1", "workspace": "<workspace_id>"}'

curl -X PATCH http://127.0.0.1:8000/api/documents/<id>/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"content": "Draft 2"}'

curl -X POST http://127.0.0.1:8000/api/documents/<id>/versions/<version_id>/restore/ \
  -H "Authorization: Token $TOKEN"
```

Restore response (abridged):

```json
{
  "document": {"id": "…", "content": "Draft 1", "version_count": 4, "…": "…"},
  "version":  {"version_number": 4, "content": "Draft 1", "restored_from": "<v1 id>", "restored_from_version": 1},
  "restored_from_version": 1
}
```

### List filters (`GET /api/documents/`)

| Param | Example | ORM |
| --- | --- | --- |
| `workspace` | `?workspace=<uuid>` | `workspace_id=` |
| `status` | `?status=published` | `status=` (validated against `Document.Status`) |
| `status_in` | `?status_in=draft,archived` | `status__in=` |
| `tag` | `?tag=planning` | `tags__name=` + `.distinct()` |
| `search` | `?search=alpha` | `Q(title__icontains) \| Q(content__icontains)` |
| `created_by` | `?created_by=<user id>` | `created_by_id=` (validated with the user model's pk type) |
| `updated_after` | `?updated_after=2026-10-01` | `updated_at__gte=` |
| `updated_before` | `?updated_before=2026-10-31T12:00:00Z` | `updated_at__lte=` (a bare date means the end of that day) |

Query parameters are validated by `DocumentFilterSerializer`. Malformed values
return 400 with a message per parameter, and so does `updated_after` later than
`updated_before`. All filtering happens in SQL, always on top of the
"workspaces I belong to" restriction.

### Postman

Import `CollabDocs.postman_collection.json` from the repository root. It covers
every endpoint, organised into folders: **Users, Workspaces, Documents,
Comments, Tags, Audit Logs**, with sample bodies for all POST, PUT and PATCH
requests.

1. Start the server (`python manage.py runserver`). The collection variable
   `base_url` defaults to `http://127.0.0.1:8000`.
2. Run the folders in order, starting with **Users**. The register requests
   create four test users (alice = admin, bob = editor, carol = viewer,
   dave = outsider) and store their tokens automatically. Later requests
   store `workspace_id`, `document_id`, `version_id`, `comment_id`, `tag_id`
   and `audit_id` for the requests that follow.
3. Every request has a status-code test. Requests named "(403)", "(401)" or
   "Outsider gets 404" check the permission rules.

The aggregation endpoints are **Workspace stats** and **Document stats**. The
signal-written audit trail is under **Audit Logs**.

---

## 7. Version numbering

* Each document's versions are numbered from **1**, independently per document
  (document A: 1, 2, 3; document B: 1, 2).
* Next number = `document.versions.count() + 1`, as the assignment requires.
* Creating a document produces version 1. **Every** successful PUT/PATCH
  produces a new version, even a status-only PATCH, which snapshots the
  unchanged content.
* **Restore never rewrites history.** Restoring version 2 of a document with
  versions 1–5 copies v2's content onto the document and creates **v6**, with
  `restored_from` pointing at v2.
* Database constraints: `UNIQUE(document, version_number)` and
  `CHECK(version_number >= 1)`.

## 8. Atomic transactions, locking and rollback

All write logic is in `documents/services.py`:

```
create:  atomic { INSERT document; n = count()+1 (=1); INSERT version n }
update:  atomic { SELECT … FOR UPDATE; n = count()+1; UPDATE document; INSERT version n }
restore: atomic { SELECT … FOR UPDATE; load old version (must belong to doc); n = count()+1;
                  UPDATE document.content; INSERT version n (restored_from = old) }
delete:  atomic { DELETE document }   -- versions removed by on_delete=CASCADE
```

* **Rollback.** If any step raises (including the version insert or a post_save
  audit receiver), the whole block rolls back. There is never a document
  without its version, or an update without its snapshot. Tests patch the
  version insert to fail and assert that nothing was written.
* **Concurrency (PostgreSQL).** `SELECT … FOR UPDATE` on the document row
  serialises writers *to the same document*: the second writer waits, then
  counts after the first has committed (READ COMMITTED). Writers to different
  documents do not block each other. The same lock also prevents lost updates.
  Two PATCHes of different fields cannot overwrite each other with stale values.
* **Safety net.** If a duplicate number still reaches the database (for example,
  a version inserted outside the service layer, or history rows deleted by hand
  so that `count()+1` collides), the unique constraint raises `IntegrityError`,
  the transaction rolls back, and the API returns **409** `version_conflict`.
  The client can simply retry.
* **Assumptions.** Versions are only created through `documents/services.py`
  (the admin inline is read-only). History rows are never deleted individually.
  The database is PostgreSQL in READ COMMITTED (Django's default).

## 9. Query optimisation

| Endpoint | Queries | Technique |
| --- | --- | --- |
| list | 3, constant in the number of rows | `select_related("workspace","created_by")`, `Prefetch("tags", only name)`, `defer("content")`, `annotate(version_count=Count("versions", distinct=True))`, membership as a `values_list` subquery |
| retrieve | 2 | select_related + tags prefetch + `Count` annotation |
| versions | 2, constant | `select_related("saved_by")`, `defer("content")`, `order_by("version_number")` |
| version detail | 2 | `select_related("document","saved_by","restored_from")` |
| stats | 4 | separate `aggregate()` per relation (no join multiplication), contributors via a `values_list(...).union(...)` count |

The user's workspace role is attached with a `Subquery` annotation
(`Document.objects.for_user`), so permission checks cost no extra query.
`documents/tests/test_queries.py` asserts these counts and checks that they do
not grow with the data.

## 10. Permissions

`documents/permissions.py` (`DocumentWorkspaceRolePermission`):

| | viewer | editor | admin |
| --- | --- | --- | --- |
| list / retrieve / versions / version detail / stats | ✓ | ✓ | ✓ |
| create / PUT / PATCH / restore | | ✓ | ✓ |
| delete | | own documents | ✓ |

Non-members get 404, never 403, so document IDs from other workspaces are not
revealed. Workspace IDs sent by clients are checked against the caller's
memberships.

---

## 11. Integration with the other apps

All references from `documents` to other apps' models go through
**`documents/integration.py`**, configured in `config/settings.py`:

```python
COLLABDOCS_WORKSPACE_MODEL        = "workspaces.Workspace"
COLLABDOCS_WORKSPACE_MEMBER_MODEL = "workspaces.WorkspaceMember"
COLLABDOCS_COMMENT_MODEL          = "comments.Comment"
COLLABDOCS_DOCUMENT_TAGS_RELATION = "tags"     # reverse of tags.Tag.documents (through DocumentTag)
```

`Document` is audited by Person C's audit app (registered in
`documents/apps.py`): exactly one `AuditLog` row per document save, written in
the same transaction, with the requesting user as actor.
`AuditSignalCompatibilityTests` assert this. The full list of cross-app
decisions is in [INTEGRATION_NOTES.md](INTEGRATION_NOTES.md).

## 12. End-to-end check

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py check_integration
python manage.py test            # all apps, on PostgreSQL
```

Then, manually or in Postman: register/login (A) → create workspace and add
an editor and a viewer (A) → create a document as editor (B) → verify one
`create` AuditLog row (C) → PATCH twice and check versions 1–3 (B) plus two
`update` audit rows (C) → tag it and filter `?tag=` (C + B) → comment, then
`GET /stats/` (C + B) → viewer PATCH = 403 → non-member GET = 404 → restore v1
and get v4 (B) → admin DELETE removes versions, comments and tag links
(cascade) → confirm no duplicate audit rows.

---

## Project layout

```
config/            settings (env-driven), root URLs
core/              access.py (roles/membership policy), context.py + middleware.py, testing.py, utils.py
users/             User model, register / login / me
workspaces/        Workspace, WorkspaceMember, members / stats
documents/
  models.py        Document, DocumentVersion, DocumentQuerySet.for_user
  services.py      transactional create / update / restore / delete
  serializers.py   document, version, restore, stats, filter-param serializers
  filters.py       list filtering (Q, icontains, gte/lte, in, distinct)
  permissions.py   workspace role policy
  views.py         DocumentViewSet (ModelViewSet + @action)
  exceptions.py    409 / safe-500 exception handler (project-wide)
  integration.py   the single seam to teammates' models
  tests/           api, transactions/audit, concurrency (PostgreSQL), query counts
comments/          Comment (threaded), list/create/detail
tags/              Tag, DocumentTag (+ Tag.documents M2M), attach/detach
audit/             AuditLog, registry + signals, read-only API, check_integration command
CollabDocs.postman_collection.json   Postman collection (all endpoints)
```