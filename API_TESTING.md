# CollabDocs — Manual API Test Guide

A step-by-step checklist for testing every API endpoint by hand against the dev server.
Each step gives the command, the **expected HTTP status**, and what to check in the response.
Steps build on each other, so run them in order.

Cast of test users:

| User | Role in the test workspace |
| --- | --- |
| `alice` | owner (creates the workspace, so she is an **admin** member) |
| `bob` | editor |
| `carol` | viewer |
| `dave` | not a member (outsider) |

---

## 0. Setup

### 0.1 Start the server

The virtual environment is `.colab`, one level **above** the project:

```
D:\CollabDocuments\
  .colab\                  <- virtual environment (packages from requirements.txt)
  CollabDocs_Combined\     <- run every command from here
```

**PowerShell**

```powershell
cd D:\CollabDocuments\CollabDocs_Combined
..\.colab\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt         # first time only (or after requirements change)
$env:DJANGO_DEBUG="true"; $env:USE_SQLITE="true"   # omit USE_SQLITE if PostgreSQL is configured in .env
python manage.py migrate
python manage.py check_integration      # expect "Integration check passed"
python manage.py runserver
```

**Git Bash**

```bash
cd /d/CollabDocuments/CollabDocs_Combined
source ../.colab/Scripts/activate
pip install -r requirements.txt         # first time only
export DJANGO_DEBUG=true USE_SQLITE=true
python manage.py migrate
python manage.py runserver
```

Check that the venv is active: `python -c "import django; print(django.get_version())"` prints `6.0.x`.
The prompt also shows `(.colab)`. Set `DJANGO_DEBUG` and `USE_SQLITE` again in every new terminal,
or put them in a `.env` file (copy `.env.example`).

Opening `http://127.0.0.1:8000/` in a browser shows **404 Not Found**. That is expected: this is an
API-only project. Use `/api/...` URLs, or `/admin/` after `python manage.py createsuperuser`.
In a browser, `http://127.0.0.1:8000/api/users/` shows DRF's browsable API (401 until you log in).

Optional, before manual testing: `python manage.py test` should end with `OK (skipped=4)`.

To start from an empty database (SQLite only): stop the server, delete `db.sqlite3`, run `migrate` again.

### 0.2 Open a second terminal (Git Bash) and define the helper

The commands below use Git Bash. In PowerShell, call `curl.exe` explicitly, or use Postman (see the end).

```bash
BASE=http://127.0.0.1:8000
api() { curl -s -X "$1" "$BASE$2" ${3:+-H "Authorization: Token $3"} ${4:+-H "Content-Type: application/json" -d "$4"} -w "\n-> HTTP %{http_code}\n"; }
```

Usage: `api METHOD /path/ [token] [json-body]`. Pass `""` as the token for anonymous calls that send a body.

> **Always keep the trailing slash** (`/api/documents/`, not `/api/documents`). Without it, Django
> returns a debug error page for POST/PUT/PATCH/DELETE because it cannot redirect those requests.

Throughout this guide, **"Save"** means copy the value from the response into a shell variable,
for example `ALICE=3f1c...`.

---

## 1. Users & authentication

| # | Command | Expect | Check |
| --- | --- | --- | --- |
| 1.1 | `api POST /api/users/ "" '{"username":"alice","email":"alice@example.com","password":"Collab#Docs2026"}'` | **201** | Response has `id` and `token`. **Save** `ALICE=<token>`, `ALICE_ID=<id>` |
| 1.2 | Same for bob: `api POST /api/users/ "" '{"username":"bob","email":"bob@example.com","password":"Collab#Docs2026"}'` | **201** | **Save** `BOB`, `BOB_ID` |
| 1.3 | Same for carol (`carol@example.com`) | **201** | **Save** `CAROL`, `CAROL_ID` |
| 1.4 | Same for dave (`dave@example.com`) | **201** | **Save** `DAVE` |
| 1.5 | `api POST /api/users/ "" '{"username":"x1","email":"alice@example.com","password":"Collab#Docs2026"}'` | **400** | "A user with this email already exists." |
| 1.6 | `api POST /api/users/ "" '{"username":"x2","email":"x2@example.com","password":"123"}'` | **400** | Password validation errors |
| 1.7 | `api POST /api/users/login/ "" '{"username":"alice","password":"Collab#Docs2026"}'` | **200** | `token` equals `$ALICE`, plus a `user` object |
| 1.8 | `api POST /api/users/login/ "" '{"username":"alice","password":"wrong"}'` | **401** | "Invalid username or password." |
| 1.9 | `api POST /api/auth/token/ "" '{"username":"bob","password":"Collab#Docs2026"}'` | **200** | `{"token": ...}` equals `$BOB` |
| 1.10 | `api GET /api/users/me/ $CAROL` | **200** | `username` is `carol` |
| 1.11 | `api GET /api/users/me/` | **401** | `"code": "not_authenticated"` |
| 1.12 | `api GET "/api/users/?search=a" $ALICE` | **200** | A plain JSON **array** (not `{count, results}`) |
| 1.13 | `api GET "/api/users/?ids=not-a-uuid" $ALICE` | **400** | Error names the `ids` parameter |
| 1.14 | `api PATCH /api/users/$BOB_ID/ $ALICE '{"first_name":"Hacker"}'` | **403** | "You can only modify your own account." |

---

## 2. Workspaces & members

| # | Command | Expect | Check |
| --- | --- | --- | --- |
| 2.1 | `api POST /api/workspaces/ $ALICE '{"name":"Team Alpha","description":"Manual test"}'` | **201** | `owner` is alice's id, `member_count` is 1. **Save** `WS=<id>` |
| 2.2 | `api POST /api/workspaces/ $ALICE '{"name":"team alpha"}'` | **400** | Duplicate name (case-insensitive, per owner) |
| 2.3 | `api POST /api/workspaces/ $ALICE '{"name":"ab"}'` | **400** | "at least 3 characters" |
| 2.4 | `api POST /api/workspaces/$WS/members/ $ALICE '{"email":"bob@example.com","role":"editor"}'` | **201** | `role` is `editor` |
| 2.5 | `api POST /api/workspaces/$WS/members/ $ALICE '{"email":"carol@example.com","role":"viewer"}'` | **201** | `role` is `viewer` |
| 2.6 | `api POST /api/workspaces/$WS/members/ $ALICE '{"email":"bob@example.com"}'` | **409** | "already a member" |
| 2.7 | `api POST /api/workspaces/$WS/members/ $ALICE '{"email":"nobody@example.com"}'` | **404** | "No user found with this email." |
| 2.8 | `api POST /api/workspaces/$WS/members/ $BOB '{"email":"dave@example.com"}'` | **403** | Editors cannot add members |
| 2.9 | `api GET /api/workspaces/$WS/members/ $CAROL` | **200** | 3 members: alice (admin), bob, carol |
| 2.10 | `api GET /api/workspaces/$WS/stats/ $CAROL` | **200** | `total_members` 3, `admins` 1, `editors` 1, `viewers` 1 |
| 2.11 | `api GET /api/workspaces/ $BOB` | **200** | Plain array containing Team Alpha |
| 2.12 | `api GET "/api/workspaces/?search=alpha&role=editor" $BOB` | **200** | Team Alpha listed (bob is an editor there) |
| 2.13 | `api GET "/api/workspaces/?created_after=yesterday" $BOB` | **400** | Error names `created_after` |
| 2.14 | `api PATCH /api/workspaces/$WS/ $CAROL '{"name":"Hacked"}'` | **403** | Viewer cannot edit |
| 2.15 | `api GET /api/workspaces/$WS/ $DAVE` | **404** | Outsider cannot see that the workspace exists |
| 2.16 | `api PATCH /api/workspaces/$WS/ $ALICE '{"description":"Updated by admin"}'` | **200** | Description changed |

---

## 3. Documents & versions

| # | Command | Expect | Check |
| --- | --- | --- | --- |
| 3.1 | `api POST /api/documents/ $BOB "{\"title\":\"API Spec\",\"content\":\"Draft 1\",\"workspace\":\"$WS\"}"` | **201** | `status` is `draft`, `version_count` 1, `created_by.username` is `bob`, `tags` is `[]`. **Save** `DOC=<id>` |
| 3.2 | `api POST /api/documents/ $CAROL "{\"title\":\"X\",\"content\":\"\",\"workspace\":\"$WS\"}"` | **403** | Viewers cannot create |
| 3.3 | `api POST /api/documents/ $DAVE "{\"title\":\"X\",\"content\":\"\",\"workspace\":\"$WS\"}"` | **400** | `workspace`: "not found or you are not a member" |
| 3.4 | `api POST /api/documents/ $BOB "{\"title\":\"X\",\"content\":\"\",\"workspace\":\"$WS\",\"created_by\":\"$ALICE_ID\"}"` | **400** | `created_by` is set by the server |
| 3.5 | `api POST /api/documents/ $BOB '{"title":"   ","workspace":"nope","status":"deleted"}'` | **400** | Field errors for `title`, `workspace`, `status`, `content` |
| 3.6 | `api PATCH /api/documents/$DOC/ $BOB '{"content":"Draft 2"}'` | **200** | `version_count` 2 |
| 3.7 | `api PUT /api/documents/$DOC/ $ALICE '{"title":"API Spec","content":"Draft 3","status":"published"}'` | **200** | `version_count` 3, `status` is `published` |
| 3.8 | `api PUT /api/documents/$DOC/ $ALICE '{"title":"Only title"}'` | **400** | PUT needs `content` |
| 3.9 | `api PATCH /api/documents/$DOC/ $CAROL '{"content":"hack"}'` | **403** | Viewer cannot edit |
| 3.10 | `api GET /api/documents/$DOC/ $DAVE` | **404** | Outsider gets 404, not 403 |
| 3.11 | `api GET /api/documents/$DOC/ $CAROL` | **200** | `content` is "Draft 3" |
| 3.12 | `api GET /api/documents/ $CAROL` | **200** | Paginated: `count`, `results`; rows have **no** `content` |
| 3.13 | `api GET "/api/documents/?workspace=$WS&status_in=draft,published&search=spec" $CAROL` | **200** | Contains the document |
| 3.14 | `api GET "/api/documents/?status=deleted&updated_after=yesterday" $CAROL` | **400** | Errors name `status` and `updated_after` |
| 3.15 | `api GET /api/documents/$DOC/versions/ $CAROL` | **200** | Plain array, `version_number` 1, 2, 3, no `content`. **Save** `V1=<id of version 1>` |
| 3.16 | `api GET /api/documents/$DOC/versions/$V1/ $CAROL` | **200** | `content` is "Draft 1" |
| 3.17 | `api POST /api/documents/$DOC/versions/$V1/restore/ $CAROL` | **403** | Viewer cannot restore |
| 3.18 | `api POST /api/documents/$DOC/versions/$V1/restore/ $BOB` | **201** | `version.version_number` 4, `restored_from_version` 1, `document.content` "Draft 1" |
| 3.19 | `api GET /api/documents/$DOC/versions/ $CAROL` | **200** | 4 versions; history 1–3 unchanged |
| 3.20 | `api GET /api/documents/$DOC/versions/not-a-uuid/ $CAROL` | **404** | Malformed version id |

---

## 4. Tags

| # | Command | Expect | Check |
| --- | --- | --- | --- |
| 4.1 | `api POST /api/workspaces/$WS/tags/ $BOB '{"name":"backend","color":"#00aa00"}'` | **201** | `document_count` 0. **Save** `TAG=<id>` (an integer) |
| 4.2 | `api POST /api/workspaces/$WS/tags/ $CAROL '{"name":"x"}'` | **403** | Viewers cannot create tags |
| 4.3 | `api POST /api/workspaces/$WS/tags/ $BOB '{"name":"BACKEND"}'` | **400** | Duplicate name (case-insensitive) |
| 4.4 | `api POST /api/workspaces/$WS/tags/ $BOB '{"name":"y","color":"red"}'` | **400** | "Color must look like #RRGGBB." |
| 4.5 | `api GET /api/workspaces/$WS/tags/ $DAVE` | **404** | Outsider |
| 4.6 | `api POST /api/documents/$DOC/tags/ $BOB "{\"tag_id\":$TAG}"` | **201** | Response has the link and the nested tag |
| 4.7 | Repeat 4.6 | **200** | Idempotent: no duplicate link |
| 4.8 | `api POST /api/documents/$DOC/tags/ $CAROL "{\"tag_id\":$TAG}"` | **403** | Viewer cannot attach |
| 4.9 | `api GET /api/workspaces/$WS/tags/ $CAROL` | **200** | `backend` has `document_count` 1 |
| 4.10 | `api GET "/api/documents/?tag=backend" $CAROL` | **200** | `count` 1; the row's `tags` is `["backend"]` |
| 4.11 | `api GET /api/documents/$DOC/ $CAROL` | **200** | `tags` is `["backend"]` |
| 4.12 | `api PATCH /api/tags/$TAG/ $CAROL '{"name":"x"}'` | **403** | Viewer cannot rename |
| 4.13 | `api PATCH /api/tags/$TAG/ $BOB '{"name":"api"}'` | **200** | `name` is `api` |
| 4.14 | `api PUT /api/tags/$TAG/ $BOB '{"name":"x"}'` | **405** | PATCH only |
| 4.15 | `api DELETE /api/documents/$DOC/tags/$TAG/ $BOB` | **204** | Detached |
| 4.16 | Repeat 4.15 | **404** | No longer attached |
| 4.17 | Repeat 4.6 | **201** | Re-attached (used in step 7) |

---

## 5. Comments

| # | Command | Expect | Check |
| --- | --- | --- | --- |
| 5.1 | `api POST /api/documents/$DOC/comments/ $CAROL "{\"body\":\"Looks good\",\"author\":\"$ALICE_ID\"}"` | **201** | `author.username` is `carol` (the `author` in the body is ignored). **Save** `C1=<id>` |
| 5.2 | `api POST /api/documents/$DOC/comments/ $BOB "{\"body\":\"Thanks\",\"parent\":$C1}"` | **201** | `parent` equals `$C1`. **Save** `R1=<id>` |
| 5.3 | `api POST /api/documents/$DOC/comments/ $CAROL "{\"body\":\"nested\",\"parent\":$R1}"` | **400** | Replies cannot have replies (`parent` error) |
| 5.4 | `api POST /api/documents/$DOC/comments/ $CAROL '{"body":""}'` | **400** | Blank body |
| 5.5 | `api GET /api/documents/$DOC/comments/ $ALICE` | **200** | `count` 1; that comment's `replies` contains bob's reply |
| 5.6 | `api GET /api/documents/$DOC/comments/ $DAVE` | **404** | Outsider |
| 5.7 | `api GET /api/comments/$C1/ $BOB` | **200** | Single comment with its replies |
| 5.8 | `api PATCH /api/comments/$C1/ $ALICE '{"body":"edited by admin"}'` | **403** | Only the author can edit, even an admin cannot |
| 5.9 | `api PATCH /api/comments/$C1/ $CAROL '{"body":"Looks great"}'` | **200** | Body updated |
| 5.10 | `api PUT /api/comments/$C1/ $CAROL '{"body":"x"}'` | **405** | PATCH only |
| 5.11 | `api DELETE /api/comments/$R1/ $CAROL` | **403** | Not the author and not an admin |
| 5.12 | `api GET /api/documents/$DOC/stats/ $CAROL` | **200** | `version_count` 4, `latest_version_number` 4, `comment_count` 2, `contributor_count` 3 |

---

## 6. Audit log

| # | Command | Expect | Check |
| --- | --- | --- | --- |
| 6.1 | `api GET /api/workspaces/$WS/audit-logs/ $ALICE` | **200** | Paginated, newest first; includes workspace, member, document, tag, comment rows |
| 6.2 | `api GET /api/workspaces/$WS/audit-logs/ $BOB` | **403** | Admins only |
| 6.3 | `api GET /api/workspaces/$WS/audit-logs/ $DAVE` | **404** | Outsider |
| 6.4 | `api GET "/api/workspaces/$WS/audit-logs/?target_type=document&action=create" $ALICE` | **200** | Exactly **1** row: `actor.username` is `bob`, `target_id` equals `$DOC` |
| 6.5 | `api GET "/api/workspaces/$WS/audit-logs/?target_type=document&action=update" $ALICE` | **200** | 3 rows (PATCH 3.6, PUT 3.7, restore 3.18); `changes` shows `from`/`to` values |
| 6.6 | `api GET "/api/workspaces/$WS/audit-logs/?actor=$CAROL_ID" $ALICE` | **200** | Only carol's actions (comment create and edit) |
| 6.7 | `api GET "/api/workspaces/$WS/audit-logs/?actor=nope" $ALICE` | **400** | Error names `actor` |
| 6.8 | `api GET "/api/workspaces/$WS/audit-logs/?created_after=2000-01-01&created_before=yesterday" $ALICE` | **400** | Error names `created_before` |
| 6.9 | Take any `id` from 6.1: `api GET /api/audit-logs/<id>/ $ALICE` | **200** | Single entry |
| 6.10 | `api GET /api/audit-logs/<id>/ $BOB` | **404** | Non-admins cannot see entries |
| 6.11 | `api POST /api/workspaces/$WS/audit-logs/ $ALICE '{}'` | **405** | Read-only API |

---

## 7. Deletes & cascades

| # | Command | Expect | Check |
| --- | --- | --- | --- |
| 7.1 | `api DELETE /api/documents/$DOC/ $CAROL` | **403** | Viewer cannot delete |
| 7.2 | Create a document as alice, then try to delete it as bob (`api DELETE /api/documents/<id>/ $BOB`) | **403** | An editor can delete only documents they created |
| 7.3 | `api DELETE /api/documents/$DOC/ $ALICE` | **204** | Admin can delete any document |
| 7.4 | `api GET /api/documents/$DOC/ $ALICE` | **404** | Gone |
| 7.5 | `api GET /api/comments/$C1/ $ALICE` | **404** | Comments were deleted with the document |
| 7.6 | `api GET "/api/workspaces/$WS/audit-logs/?action=delete&actor=$ALICE_ID" $ALICE` | **200** | Delete rows for the `document`, both `comment`s, and the `documenttag` link |
| 7.7 | `api GET /api/workspaces/$WS/tags/ $BOB` | **200** | Tag still exists, `document_count` 0 |
| 7.8 | `api DELETE /api/tags/$TAG/ $BOB` | **204** | Editors can delete tags |

### 7.9 Account self-delete (cascade)

```bash
api POST /api/users/ "" '{"username":"eve","email":"eve@example.com","password":"Collab#Docs2026"}'   # save EVE, EVE_ID
api POST /api/workspaces/ $EVE '{"name":"Eve Space"}'                                                    # save EVE_WS
api POST /api/documents/ $EVE "{\"title\":\"Eve doc\",\"content\":\"x\",\"workspace\":\"$EVE_WS\"}"       # save EVE_DOC
api POST /api/documents/$EVE_DOC/comments/ $EVE '{"body":"mine"}'
api DELETE /api/users/$EVE_ID/ $DAVE      # expect 403 (cannot delete someone else)
api DELETE /api/users/$EVE_ID/ $EVE       # expect 204 (workspace, document, comment cascade)
api GET /api/users/me/ $EVE               # expect 401 (token removed with the user)
```

The 204 matters: deleting an account cascades into audited rows, and before the integration
fix this request failed. The audit rows it writes have `actor = null`. To inspect them:

```bash
python manage.py shell -c "from audit.models import AuditLog; [print(r.action, r.target_type, r.actor_id) for r in AuditLog.objects.filter(workspace_id='<EVE_WS>')]"
```

---

## 8. Things that should never happen

While testing, any of these means a bug:

- A **500** response, or an HTML debug page (apart from a URL missing its trailing slash, see 0.2).
- A non-member getting **403** instead of **404** for anything inside a workspace (that would leak its existence).
- More than one audit row for a single create, update or delete.
- Version numbers repeating or skipping for one document.
- An audit row whose `actor` is not the user who made the request.

---

## 9. Quick reference

| Area | Endpoint | Who |
| --- | --- | --- |
| Register / login | `POST /api/users/`, `POST /api/users/login/`, `POST /api/auth/token/` | anyone |
| Me / users | `GET /api/users/me/`, `GET /api/users/`, `PATCH/DELETE /api/users/{uuid}/` | logged in (edit or delete: self only) |
| Workspaces | `GET/POST /api/workspaces/`, `GET/PUT/PATCH/DELETE /api/workspaces/{uuid}/` | member reads, admin writes |
| Members / stats | `GET/POST /api/workspaces/{uuid}/members/`, `GET /api/workspaces/{uuid}/stats/` | member reads, admin adds |
| Documents | `GET/POST /api/documents/`, `GET/PUT/PATCH/DELETE /api/documents/{uuid}/` | member reads; editor or admin writes; delete: admin, or the editor who created it |
| Versions | `GET .../versions/`, `GET .../versions/{uuid}/`, `POST .../versions/{uuid}/restore/` | member reads, editor or admin restores |
| Doc stats | `GET /api/documents/{uuid}/stats/` | member |
| Tags | `GET/POST /api/workspaces/{uuid}/tags/`, `GET/PATCH/DELETE /api/tags/{id}/` | member reads, editor or admin writes |
| Tag links | `POST /api/documents/{uuid}/tags/`, `DELETE /api/documents/{uuid}/tags/{id}/` | editor or admin |
| Comments | `GET/POST /api/documents/{uuid}/comments/`, `GET/PATCH/DELETE /api/comments/{id}/` | member; edit: author; delete: author or admin |
| Audit | `GET /api/workspaces/{uuid}/audit-logs/`, `GET /api/audit-logs/{id}/` | admin |

Workspace, document, version and user ids are **UUIDs**; tag, comment and audit-log ids are **integers**.

### Postman

`postman/CollabDocs_PersonB_Documents.postman_collection.json` covers the documents and versions
endpoints. Set `base_url` to `http://127.0.0.1:8000`, run **Auth → Obtain token** (or paste
`$BOB`), and set `workspace_id` to `$WS`.
