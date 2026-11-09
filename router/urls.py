from django.urls import path

from . import views

app_name = "router"

urlpatterns = [
    path("", views.RoutingRulesView.as_view(), name="rules"),
    path("settings/", views.RoutingSettingsUpdateView.as_view(), name="settings"),
    path("rules/new/", views.RuleCreateView.as_view(), name="rule_create"),
    path("rules/<int:pk>/edit/", views.RuleUpdateView.as_view(), name="rule_edit"),
    path("rules/<int:pk>/delete/", views.RuleDeleteView.as_view(), name="rule_delete"),
    path("requests/", views.RoutedRequestsView.as_view(), name="requests"),
    path("explain/<int:log_id>/", views.ExplainView.as_view(), name="explain"),
    path("api/preview", views.PreviewAPIView.as_view(), name="api_preview"),
]
