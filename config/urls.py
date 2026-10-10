from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path("admin/", admin.site.urls),
    # TEMPORARY token login for standalone testing; Person A's auth endpoint replaces it.
    path("api/auth/token/", obtain_auth_token, name="api-token"),
    path("api/", include("documents.urls")),
]
