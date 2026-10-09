# CollabDocs API: Users and Workspaces (Person A)

Base URL: `http://127.0.0.1:8000`
Auth: `Authorization: Token <token>` (get the token from Register or Login).
Roles in a workspace: `admin`, `editor`, `viewer`.

## Users

| # | Method | Path | Auth | Description |
|---|--------|------|------|-------------|
| 1 | POST | `/api/users/` | No | Register. Returns user and token |
| 2 | POST | `/api/users/login/` | No | Login. Returns token |
| 3 | GET | `/api/users/me/` | Yes | Current user |
| 4 | GET | `/api/users/` | Yes | List users. Filters: `search`, `ids`, `joined_after` |
| 5 | PATCH/PUT | `/api/users/{id}/` | Self only | Update own profile |
| 6 | DELETE | `/api/users/{id}/` | Self only | Delete own account |

**Register body**
```json
{"username": "prasanth", "email": "prasanth@example.com", "password": "StrongPass#123", "first_name": "Prasanth", "last_name": "V"}
```
Responses: `201` created, `400` validation error (duplicate email, weak password, password contains username).

**Login body**: `{"username": "prasanth", "password": "StrongPass#123"}`. Responses: `200`, `401` invalid credentials.

## Workspaces

| # | Method | Path | Who can call | Description |
|---|--------|------|--------------|-------------|
| 7 | POST | `/api/workspaces/` | Any logged-in user | Create workspace. Owner becomes `admin` member (one atomic transaction) |
| 8 | GET | `/api/workspaces/` | Logged-in | My workspaces. Filters: `search`, `is_active`, `role` (comma list), `created_after`, `created_before` |
| 9 | GET | `/api/workspaces/{id}/` | Member | Workspace detail |
| 10 | PUT/PATCH | `/api/workspaces/{id}/` | Admin | Update workspace |
| 11 | DELETE | `/api/workspaces/{id}/` | Admin | Delete workspace |
| 12 | GET | `/api/workspaces/{id}/members/` | Member | List members |
| 13 | POST | `/api/workspaces/{id}/members/` | Admin | Add member by email |
| 14 | GET | `/api/workspaces/{id}/stats/` | Member | Member counts by role (aggregate) |

**Create body**: `{"name": "Engineering Team", "description": "Docs for the team"}`

**Add member body**: `{"email": "anita@example.com", "role": "editor"}`

**Stats response**
```json
{"total_members": 2, "admins": 1, "editors": 1, "viewers": 0, "workspace_id": "...", "name": "Engineering Team", "is_active": true}
```

## Status codes
`200` OK, `201` created, `204` deleted, `400` validation error, `401` not logged in or bad credentials,
`403` role not allowed, `404` not found (or not a member), `409` duplicate member.
