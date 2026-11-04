from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.UsageDashboardView.as_view(), name="dashboard"),
    path("export.csv", views.UsageCSVView.as_view(), name="export_csv"),
    path("limits/", views.UsageLimitView.as_view(), name="limits"),
]
