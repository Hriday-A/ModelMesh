from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("keys/", views.APIKeyListView.as_view(), name="api_keys"),
    path("keys/<int:pk>/revoke/", views.APIKeyRevokeView.as_view(), name="revoke_key"),
    path("playground/", views.PlaygroundView.as_view(), name="playground"),
    path("history/", views.RequestHistoryView.as_view(), name="history"),
    path("history/<int:pk>/", views.RequestDetailView.as_view(), name="request_detail"),
    path("api/chat", views.ChatAPIView.as_view(), name="api_chat"),
]
