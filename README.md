# CollabDocs — Documents & Versions (Person B)

API-only Django REST Framework service for **documents and their version
history**, part of the CollabDocs group project (a simplified Notion /
Google Docs). This repository is Person B's standalone implementation. It
runs and tests on its own and is structured so it can be merged with Person A's
(users/workspaces) and Person C's (comments/tags/audit) apps.

| App | Owner | Status |
| --- | --- | --- |
| `documents/` | Person B | **Final**: models, services, API, tests |
| `compat/` | stand-ins for Persons A and C | **Temporary**: delete at integration |
| `config/` | shared | project settings and URLs, to be merged |

Stack: Python 3.14, Django 6.0, DRF 3.18, PostgreSQL (psycopg 3).

---

## 1. Installation

```bash
python -m venv .collabenv
# Windows: .collabenv\Scripts\activate     macOS/Linux: source .collabenv/bin/activate
pip install -r requirements.txt
```

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
| `USE_SQLITE` | `true` only on a machine without PostgreSQL (see the testing notes) |

## 3. Create the PostgreSQL database

```sql
-- psql -U postgres
CREATE USER collabdocs WITH PASSWORD 'change-me';
CREATE DATABASE collabdocs OWNER collabdocs;
ALTER USER collabdocs CREATEDB;   -- lets the test runner create test_collabdocs
```

## 4. Migrate, seed, run

```bash
python manage.py migrate
python manage.py seed_demo        # demo users, workspace, tags, tokens (prints the IDs)
python manage.py runserver
```

`seed_demo` creates `alice` (admin), `bob` (editor), `carol` (viewer) and
`dave` (not a member) with password `collabdocs-demo-123`, and prints each
user's API token and the `workspace_id`.

## 5. Tests

```bash
python manage.py test documents             # against PostgreSQL (recommended)
USE_SQLITE=true python manage.py test documents   # no PostgreSQL available
```

* 56 tests: CRUD, versioning, restore, filters, permissions, error codes,
  rollback, the audit-signal contract, query counts, and concurrency.
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
| POST | `/api/auth/token/` | — | **temporary** login for standalone use |

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
TOKEN=...   # from seed_demo
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

Import `postman/CollabDocs_PersonB_Documents.postman_collection.json`. Set
`base_url`, then either run **Auth → Obtain token** or paste a token from
`seed_demo`, and set `workspace_id`. "Create document" stores `document_id`
and "List versions" stores `version_id`. Every request has status-code tests
and saved example responses.

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

## 11. Temporary compatibility models

`compat/` exists only so this app runs without teammates' code:

| Temporary model / code | Real owner | Fields relied on |
| --- | --- | --- |
| `compat.Workspace` | Person A | UUID `id` |
| `compat.WorkspaceMember` | Person A | `workspace`, `user`, `role` ∈ {admin, editor, viewer} |
| `compat.Tag` | Person C | `name`; M2M to Document, reverse name `tags` |
| `compat.Comment` | Person C | `document` FK (`related_name="comments"`), `author` FK |
| `compat.AuditLog` + `compat/signals.py` | Person C | the audit signal stand-in |
| `compat` `seed_demo` command | — | demo data |
| `/api/auth/token/` in `config/urls.py` | Person A | standalone login |

The user model is never redefined: everything uses `settings.AUTH_USER_MODEL`,
so a custom user model from Person A (UUID or int pk) works unchanged.

All references from `documents` to these models go through
**`documents/integration.py`**, which reads these settings:

```python
COLLABDOCS_WORKSPACE_MODEL        = "compat.Workspace"        # default
COLLABDOCS_WORKSPACE_MEMBER_MODEL = "compat.WorkspaceMember"
COLLABDOCS_COMMENT_MODEL          = "compat.Comment"
COLLABDOCS_DOCUMENT_TAGS_RELATION = "tags"     # None disables tag prefetch/filter
COLLABDOCS_COMMENT_AUTHOR_FIELD   = "author"
```

---

## 12. Final integration (with Persons A and C)

**1. Temporary code to remove.** The whole `compat/` app (models, migrations,
signals, admin, `seed_demo`), the `"compat"` entry in `INSTALLED_APPS`, and
the `/api/auth/token/` route if Person A provides login.

**2. ForeignKeys to redirect.** In `config/settings.py`, set
`COLLABDOCS_WORKSPACE_MODEL`, `COLLABDOCS_WORKSPACE_MEMBER_MODEL` and
`COLLABDOCS_COMMENT_MODEL` to the real labels (for example `"workspaces.Workspace"`).
`Document.workspace` reads the label at import time. `created_by` and
`saved_by` already use `AUTH_USER_MODEL`. Person C's `Tag` (M2M with
`related_name="tags"`) and `Comment` (FK with `related_name="comments"`) must
point **to** `documents.Document`. If their names differ, set
`COLLABDOCS_DOCUMENT_TAGS_RELATION` / `COLLABDOCS_COMMENT_AUTHOR_FIELD`. If
Person A's membership model uses different field names than
`workspace/user/role`, adapt the three functions in `documents/integration.py`.
That is the only place to change.

**3. Permissions.** `DocumentWorkspaceRolePermission` is document-specific, so
keep it. It gets roles from `integration.get_role()` and from the
`user_role` annotation in `DocumentQuerySet.for_user()`, both built on the
membership model. If Person A ships a shared helper (for example
`get_workspace_role(user, workspace)`), call it from `integration.get_role()`.
Do not import their classes directly into views.

**4. Signals: avoid duplicate audit rows.** Person C's `post_save` receiver for
`Document` replaces `compat/signals.py`. Removing the `compat` app
disconnects the stand-in. Never register both. Re-run
`AuditSignalCompatibilityTests` (pointing `factories.audit_log_model()` at Person
C's model): it asserts **exactly one** row per save, with action `created`/`updated`,
`model_name="Document"`, `object_id=str(uuid)`, actor `created_by`. Person C's
receiver must write with the default connection and must **not** use
`transaction.on_commit` if the audit row has to roll back together with the document.

**5. Apps and URLs.** `INSTALLED_APPS` must include `"documents"` after the
apps it references (workspaces, users). In the combined `config/urls.py`, add
`path("api/", include("documents.urls"))`. The router only registers
`documents/`, so it does not collide with other routers mounted under `api/`.
Also merge `REST_FRAMEWORK`: keep a single `EXCEPTION_HANDLER`. Ours
(`documents.exceptions.api_exception_handler`) is generic (409 for
IntegrityError, safe 500, `code` field). Either adopt it project-wide or move
its IntegrityError branch into the shared handler. Agree on one
`DEFAULT_AUTHENTICATION_CLASSES` (Token vs JWT); the documents code does not
depend on which one is used.

**6. Requirements.** Merge into one pinned `requirements.txt`. Pick a single
Django, DRF and psycopg version. This code uses only stable APIs
(`CheckConstraint(condition=...)` needs Django ≥ 5.1).

**7. Migrations.** `documents/migrations/0001_initial.py` depends on
`compat.0001_initial` and points `Document.workspace` at `compat.workspace`.
`compat.0002` depends on `documents.0001` (Tag/Comment → Document).
*If no shared database has applied these migrations* (the expected case):
delete `compat/` and `documents/migrations/0001_initial.py`, change the
settings above, and run `python manage.py makemigrations documents` to
generate a fresh `0001` whose dependencies are Person A's workspace migration
and `AUTH_USER_MODEL`. Person C's Tag/Comment migrations then depend on
`documents.0001`. Run `makemigrations --check` and `migrate` on an empty database.
*If they have already been applied somewhere you must keep*: do **not** delete
them. Add a new migration (`documents.0002`) that `AlterField`s
`Document.workspace` to the real model. Copy or re-map workspace rows first,
because the FK constraint will be re-created. Then remove `compat` with a
migration that deletes its models, before taking it out of `INSTALLED_APPS`.
Any applied migration that is later deleted must also be removed from
`django_migrations` with `migrate --fake`. Never hand-edit an applied migration.

**8. Settings and PostgreSQL.** Consolidate on one `settings.py` using the same
`POSTGRES_*` variables (or translate them to whatever the team chose) and one
`.env.example`. Keep `USE_TZ=True`. The database user needs `CREATEDB` for the
test runner.

**9. Postman.** Import the shared collection and this one. Move the Documents
and Versions folders in, drop "Auth (temporary)" in favour of Person A's login
request, and share the `base_url`, `token` and `workspace_id` variables.

**10. End-to-end checks after merging.**

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test            # all apps, on PostgreSQL
```

Then, manually or in Postman: register/login (A) → create workspace and invite
an editor and a viewer (A) → create a document as editor (B) → verify one
`created` AuditLog row (C) → PATCH twice and check versions 1–3 (B) plus two
`updated` audit rows (C) → tag it and filter `?tag=` (C + B) → comment, then
`GET /stats/` (C + B) → viewer PATCH = 403 → non-member GET = 404 → restore v1
and get v4 (B) → admin DELETE removes versions, comments and tag links
(cascade) → confirm no duplicate audit rows.

---

## Project layout

```
config/            settings (env-driven), root URLs
documents/
  models.py        Document, DocumentVersion, DocumentQuerySet.for_user
  services.py      transactional create / update / restore / delete
  serializers.py   document, version, restore, stats, filter-param serializers
  filters.py       list filtering (Q, icontains, gte/lte, in, distinct)
  permissions.py   workspace role policy
  views.py         DocumentViewSet (ModelViewSet + @action)
  exceptions.py    409 / safe-500 exception handler
  integration.py   the single seam to teammates' models
  tests/           api, transactions/audit, concurrency (PostgreSQL), query counts
compat/            TEMPORARY stand-ins + seed_demo
postman/           Person B Postman collection
```
