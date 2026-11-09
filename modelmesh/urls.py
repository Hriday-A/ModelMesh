from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # login/, logout/, password_change/ ... from Django's built-in auth views
    path("", include("django.contrib.auth.urls")),
    path("", include("accounts.urls")),
    path("usage/", include("analytics.urls")),
    path("providers/", include("providers.urls")),
    path("routing/", include("router.urls")),
]
