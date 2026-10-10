# CollabDocs Backend (Django REST Framework)

Person A part: project foundation, Users, Workspaces, members/roles, permissions, middleware.

## Setup
```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env           # SQLite is used by default, no database setup needed
python manage.py migrate
python manage.py createsuperuser   # optional
python manage.py runserver
```
Server: http://127.0.0.1:8000  (middleware logs appear in this console)

## Tests
```bash
python manage.py test
```

## API docs and Postman
- Endpoint reference: `API_DOCS.md`
- Postman collection: `CollabDocs.postman_collection.json` (import it, run Register or Login first)

## Demo video
Link: _add Loom / Google Drive link here_

## Database
SQLite by default. To switch to PostgreSQL, set `DB_ENGINE` and the `DB_*` values in `.env`.
