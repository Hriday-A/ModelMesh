import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import APIKey, RequestLog, UserProfile
from .services import ProviderError


def failing_router(prompt, priority):
    raise ProviderError("All providers are down.")


@override_settings(MODELMESH_PROVIDER="mock", MODELMESH_ROUTER="accounts.services.default_router")
class AccountsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", "alice@illinois.edu", "s3cure-pass-123")
        self.other = User.objects.create_user("bob", "bob@illinois.edu", "s3cure-pass-123")


class SignUpTests(AccountsTestCase):
    def test_signup_creates_profile_and_logs_in(self):
        response = self.client.post(reverse("accounts:signup"), {
            "username": "carol",
            "email": "carol@illinois.edu",
            "password1": "another-pass-456",
            "password2": "another-pass-456",
        })
        self.assertRedirects(response, reverse("accounts:playground"))
        carol = User.objects.get(username="carol")
        self.assertTrue(UserProfile.objects.filter(user=carol).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), carol.pk)

    def test_signup_rejects_duplicate_email(self):
        response = self.client.post(reverse("accounts:signup"), {
            "username": "alice2",
            "email": "ALICE@illinois.edu",
            "password1": "another-pass-456",
            "password2": "another-pass-456",
        })
        self.assertContains(response, "already exists")


class APIKeyTests(AccountsTestCase):
    def test_only_hash_is_stored(self):
        api_key, raw_key = APIKey.generate(self.user, "test")
        self.assertTrue(raw_key.startswith("mm_"))
        self.assertNotEqual(api_key.hashed_key, raw_key)
        self.assertEqual(APIKey.authenticate(raw_key), api_key)

    def test_revoked_key_does_not_authenticate(self):
        api_key, raw_key = APIKey.generate(self.user, "test")
        api_key.revoked = True
        api_key.save()
        self.assertIsNone(APIKey.authenticate(raw_key))

    def test_new_key_shown_once(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:api_keys"), {"name": "laptop"}, follow=True)
        raw_key = response.context["new_raw_key"]
        self.assertContains(response, raw_key)
        self.assertNotContains(self.client.get(reverse("accounts:api_keys")), raw_key)

    def test_cannot_revoke_someone_elses_key(self):
        api_key, _ = APIKey.generate(self.other, "bob's key")
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:revoke_key", args=[api_key.pk]))
        self.assertEqual(response.status_code, 404)
        api_key.refresh_from_db()
        self.assertFalse(api_key.revoked)

    def test_active_key_limit(self):
        for i in range(5):
            APIKey.generate(self.user, f"key {i}")
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:api_keys"), {"name": "one too many"})
        self.assertContains(response, "at most 5 active keys")


class PlaygroundTests(AccountsTestCase):
    def test_requires_login(self):
        response = self.client.get(reverse("accounts:playground"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('accounts:playground')}")

    def test_prompt_is_answered_and_logged(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:playground"), {"prompt": "Hello there", "priority": "cheapest"})
        self.assertContains(response, "Mock response")
        log = RequestLog.objects.get(user=self.user)
        self.assertEqual(log.status, "success")
        self.assertEqual(log.source, "playground")
        self.assertEqual(log.priority, "cheapest")
        self.assertEqual(log.model_used, "mock-echo")

    def test_blank_prompt_rejected(self):
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:playground"), {"prompt": "   ", "priority": "balanced"})
        self.assertFalse(RequestLog.objects.exists())

    @override_settings(MODELMESH_ROUTER="accounts.tests.failing_router")
    def test_provider_failure_is_logged_not_crashed(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:playground"), {"prompt": "Hi", "priority": "balanced"})
        self.assertContains(response, "All providers are down.")
        self.assertEqual(RequestLog.objects.get().status, "error")


class HistoryTests(AccountsTestCase):
    def setUp(self):
        super().setUp()
        RequestLog.objects.create(user=self.user, source="playground", prompt="python question", status="success")
        RequestLog.objects.create(user=self.user, source="api", prompt="sql question", status="error")
        RequestLog.objects.create(user=self.other, source="api", prompt="bob's secret", status="success")
        self.client.force_login(self.user)

    def test_shows_only_own_requests(self):
        response = self.client.get(reverse("accounts:history"))
        self.assertEqual(len(response.context["logs"]), 2)
        self.assertNotContains(response, "bob&#x27;s secret")

    def test_filters(self):
        response = self.client.get(reverse("accounts:history"), {"q": "python"})
        self.assertEqual([log.prompt for log in response.context["logs"]], ["python question"])
        response = self.client.get(reverse("accounts:history"), {"status": "error"})
        self.assertEqual([log.prompt for log in response.context["logs"]], ["sql question"])

    def test_cannot_view_someone_elses_request(self):
        bobs = RequestLog.objects.get(user=self.other)
        response = self.client.get(reverse("accounts:request_detail", args=[bobs.pk]))
        self.assertEqual(response.status_code, 404)


class ChatAPITests(AccountsTestCase):
    def setUp(self):
        super().setUp()
        self.api_key, self.raw_key = APIKey.generate(self.user, "test")
        self.url = reverse("accounts:api_chat")

    def post(self, body, key=None):
        return self.client.post(
            self.url,
            data=json.dumps(body) if not isinstance(body, str) else body,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {key or self.raw_key}",
        )

    def test_valid_request(self):
        response = self.post({"prompt": "What is Django?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["model"], "mock-echo")
        self.assertIn("usage", data)
        log = RequestLog.objects.get(pk=data["id"])
        self.assertEqual(log.source, "api")
        self.assertEqual(log.api_key, self.api_key)

    def test_missing_or_bad_key(self):
        self.assertEqual(self.client.post(self.url, {}, content_type="application/json").status_code, 401)
        self.assertEqual(self.post({"prompt": "hi"}, key="mm_wrong").status_code, 401)

    def test_bad_body(self):
        self.assertEqual(self.post("not json").status_code, 400)
        self.assertEqual(self.post({"prompt": ""}).status_code, 400)
        self.assertEqual(self.post({"prompt": "hi", "priority": "random"}).status_code, 400)

    @override_settings(MODELMESH_ROUTER="accounts.tests.failing_router")
    def test_provider_failure_returns_502(self):
        response = self.post({"prompt": "hi"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "All providers are down.")
