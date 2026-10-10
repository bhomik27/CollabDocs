from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/token/", obtain_auth_token, name="api-token"),
    path("api/", include("users.urls")),
    path("api/", include("workspaces.urls")),
    path("api/", include("documents.urls")),
    path("api/", include("comments.urls")),
    path("api/", include("tags.urls")),
    path("api/", include("audit.urls")),
]
