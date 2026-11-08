from django.urls import path

from . import views

app_name = "providers"

urlpatterns = [
    path("", views.ProviderListView.as_view(), name="list"),
    path("new/", views.ProviderFormView.as_view(), name="create"),
    path("<int:pk>/edit/", views.ProviderFormView.as_view(), name="edit"),
    path("<int:pk>/check/", views.ProviderHealthCheckView.as_view(), name="check"),
]
