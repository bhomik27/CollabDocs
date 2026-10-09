"""
Standalone settings for developing Person C's apps (comments, tags, audit).

MERGE NOTE: on merge day you do NOT replace the team's settings.py with this file.
Copy only the lines marked ">>> PERSON C" into the team settings (see INTEGRATION.md).
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# >>> STUB ONLY - delete this line on merge. It makes the stub `workspaces` and
# `documents` apps importable so Person C can work before A and B push their code.
sys.path.insert(0, str(BASE_DIR / "STUBS_DO_NOT_MERGE"))

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    # >>> STUB ONLY - replaced by Person A's and Person B's real apps on merge
    "workspaces",
    "documents",
    # >>> PERSON C
    "comments",
    "tags",
    "audit",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # >>> PERSON C (stand-in for Person A's request-logging middleware; see INTEGRATION.md)
    "core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# SQLite by default so the project runs anywhere; set DB_NAME to use PostgreSQL.
if os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

# >>> PERSON C needs: authenticated-by-default, and pagination (list endpoints return
# {"count", "next", "previous", "results"}). Person A's JWT/Token auth class replaces the two
# stand-in auth classes below.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}
