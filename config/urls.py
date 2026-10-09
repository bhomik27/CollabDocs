"""
Root URL configuration.

All of Person C's routes live under /api/. Person A and Person B will add their own
include() lines to the same list on merge (see INTEGRATION.md).
"""
from django.urls import include, path

urlpatterns = [
    # >>> PERSON C
    path("api/", include("comments.urls")),
    path("api/", include("tags.urls")),
    path("api/", include("audit.urls")),
]
