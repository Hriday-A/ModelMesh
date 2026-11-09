"""Router tests. The Lumen call and the embedder are replaced with test doubles,
so tests run offline and free. None of this touches the benchmark data."""

import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

import joblib
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import APIKey, RequestLog
from accounts.services import ProviderError, run_prompt

from .models import Feedback, RouterModel, RoutingDecision, RoutingRule, RoutingSettings
from .scoring import PRIORITY_WEIGHTS, apply_confidence_gate, blend_feedback, score_candidates
from .services import decide
from .training import fit_artifact

SMALL, MEDIUM, LARGE = "ornith-1.0-35b", "deepseek-v4-flash", "glm-5.3"


def fake_embed(texts):
    """Tiny stand-in for the sentence embedder: a few hand-made features."""
    import numpy as np

    rows = []
    for t in texts:
        low = t.lower()
        rows.append([float("code" in low or "def " in low), float(low.startswith(("hi", "hello", "thanks"))), len(t) / 100, 1.0])
    return np.array(rows)


def fake_answer(model_id, prompt):
    return {"text": f"answer from {model_id}", "input_tokens": 100, "output_tokens": 200, "latency_ms": 50, "stop_reason": "end_turn"}


def build_artifact(path):
    texts = ["hi", "hello there", "thanks!", "def foo(): fix this code bug", "write code for a parser", "debug my code traceback"]
    artifact = fit_artifact(
        texts,
        ["chat", "chat", "chat", "coding", "coding", "coding"],
        {SMALL: [1, 1, 1, 0, 0, 0], MEDIUM: [1, 1, 1, 1, 1, 0], LARGE: [1, 1, 1, 1, 1, 1]},
        fake_embed,
        "fake-embedder",
    )
    joblib.dump(artifact, path)
    return artifact


class RouterTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.artifact_path = str(Path(self.tmp.name) / "router.joblib")
        self.settings_override = override_settings(
            ROUTER_ARTIFACT_PATH=self.artifact_path, MODELMESH_ROUTER="router.services.route"
        )
        self.settings_override.enable()
        self.embed_patch = mock.patch("router.classifier.embed", side_effect=fake_embed)
        self.embed_patch.start()
        self.user = User.objects.create_user("sam", password="pass-12345-x")
        self.models = {m.model_id: m for m in RouterModel.objects.all()}

    def tearDown(self):
        self.embed_patch.stop()
        self.settings_override.disable()
        self.tmp.cleanup()


class RuleMatchingTests(RouterTestCase):
    def test_keywords_match_whole_words_only(self):
        rule = RoutingRule(category="chat", keywords="hi, how are you", preferred_model=self.models[SMALL])
        self.assertEqual(rule.matches("Hi, how are you?"), "hi")
        self.assertEqual(rule.matches("so, how are you doing"), "how are you")
        self.assertIsNone(rule.matches("Is this a bug? Which line?"))


class ScoringTests(RouterTestCase):
    def ranked(self, probs, priority):
        rows = score_candidates(list(self.models.values()), probs, PRIORITY_WEIGHTS[priority], {m: None for m in self.models})
        return apply_confidence_gate(rows, 0.6)

    def test_easy_prompt_goes_to_cheapest_when_balanced(self):
        order, gated = self.ranked({SMALL: 0.96, MEDIUM: 0.97, LARGE: 0.98}, "balanced")
        self.assertEqual(order[0]["model_id"], SMALL)
        self.assertFalse(gated)

    def test_best_quality_picks_the_most_likely_model(self):
        order, _ = self.ranked({SMALL: 0.95, MEDIUM: 0.97, LARGE: 0.98}, "quality")
        self.assertEqual(order[0]["model_id"], LARGE)

    def test_confidence_gate_skips_a_cheap_model_that_will_probably_fail(self):
        order, gated = self.ranked({SMALL: 0.55, MEDIUM: 0.50, LARGE: 0.90}, "cheapest")
        self.assertTrue(gated)
        self.assertNotEqual(order[0]["model_id"], SMALL)
        self.assertGreaterEqual(order[0]["p_good"], 0.6)

    def test_measured_cost_per_answer_replaces_list_price(self):
        # The small model is cheapest per token but, say, writes 20x more thinking tokens.
        measured = {SMALL: 0.0020, MEDIUM: 0.0004, LARGE: 0.0010}
        rows = score_candidates(list(self.models.values()), {SMALL: 0.95, MEDIUM: 0.95, LARGE: 0.95},
                                PRIORITY_WEIGHTS["cheapest"], {m: None for m in self.models}, measured)
        self.assertEqual(rows[0]["model_id"], MEDIUM)
        self.assertEqual(next(r for r in rows if r["model_id"] == SMALL)["price"], 1.0)

    def test_list_price_is_used_until_every_model_is_measured(self):
        rows = score_candidates(list(self.models.values()), {SMALL: 0.95, MEDIUM: 0.95, LARGE: 0.95},
                                PRIORITY_WEIGHTS["cheapest"], {m: None for m in self.models}, {SMALL: 0.002})
        self.assertEqual(rows[0]["model_id"], SMALL)

    def test_feedback_moves_probability_toward_ratings(self):
        self.assertEqual(blend_feedback(0.9, None, 0), 0.9)
        self.assertLess(blend_feedback(0.9, 1.0, 10), 0.5)


class TrainingTests(TestCase):
    def test_single_class_labels_become_a_constant_probability(self):
        artifact = build_artifact(Path(tempfile.mkdtemp()) / "a.joblib")
        self.assertEqual(artifact["models"][LARGE]["kind"], "constant")
        self.assertAlmostEqual(artifact["models"][LARGE]["p"], 7 / 8)
        self.assertEqual(artifact["models"][SMALL]["kind"], "logistic")


class DecideTests(RouterTestCase):
    def test_without_a_trained_model_keyword_rules_are_used(self):
        decision = decide("hi there", "balanced")
        self.assertEqual(decision.classifier_used, "keyword_fallback")
        self.assertEqual(decision.order[0].model_id, SMALL)
        self.assertEqual(decide("Prove that the algorithm is optimal step by step", "balanced").order[0].model_id, LARGE)

    def test_trained_classifier_is_used_when_available(self):
        build_artifact(self.artifact_path)
        decision = decide("write code to fix this bug", "balanced")
        self.assertEqual(decision.classifier_used, "trained")
        self.assertEqual({r["model_id"] for r in decision.scores}, set(self.models))
        self.assertIn("chance of a good answer", decision.reason(decision.order[0]))

    def test_broken_artifact_falls_back_to_keywords(self):
        Path(self.artifact_path).write_text("not a model")
        self.assertEqual(decide("hi", "balanced").classifier_used, "keyword_fallback")

    def test_rule_puts_its_preferred_model_first(self):
        RoutingRule.objects.create(category="coding", keywords="segfault", preferred_model=self.models[LARGE],
                                   fallback_model=self.models[MEDIUM])
        decision = decide("hi, why do I get a segfault?", "cheapest")
        self.assertEqual([m.model_id for m in decision.order[:2]], [LARGE, MEDIUM])
        self.assertEqual(decision.category, "coding")

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(ProviderError):
            decide("   ", "balanced")


@mock.patch("router.llm.complete", side_effect=fake_answer)
class RunPromptTests(RouterTestCase):
    def test_decision_is_saved_and_cost_uses_the_chosen_models_price(self, _complete):
        log = run_prompt(self.user, "hi there", source="playground", priority="balanced")
        decision = RoutingDecision.objects.get(request_log=log)
        expected = self.models[log.model_used].cost(100, 200).quantize(Decimal("0.000001"))
        self.assertEqual(log.status, "success")
        self.assertEqual(RequestLog.objects.get(pk=log.pk).cost_usd, expected)
        self.assertEqual(log.cost_usd, expected)
        self.assertGreater(decision.saved_usd, 0)
        self.assertFalse(decision.fallback_used)

    def test_failover_tries_the_next_model(self, complete):
        def flaky(model_id, prompt):
            if model_id == SMALL:
                raise ProviderError("The provider is rate limiting requests. Try again shortly.")
            return fake_answer(model_id, prompt)

        complete.side_effect = flaky
        log = run_prompt(self.user, "hi there", source="playground", priority="balanced")
        decision = log.routing_decision
        self.assertEqual(log.status, "success")
        self.assertNotEqual(log.model_used, SMALL)
        self.assertTrue(decision.fallback_used)
        self.assertEqual(decision.attempts[0]["model_id"], SMALL)

    def test_all_models_failing_is_logged_as_an_error(self, complete):
        complete.side_effect = ProviderError("down")
        log = run_prompt(self.user, "hi there", source="api", priority="balanced")
        self.assertEqual(log.status, "error")
        self.assertIn("All models failed", log.error_message)
        self.assertIsNone(log.routing_decision.chosen_model)
        self.assertEqual(len(log.routing_decision.attempts), 3)

    def test_feedback_changes_future_probabilities(self, _complete):
        build_artifact(self.artifact_path)
        before = decide("hi", "balanced")
        for _ in range(10):
            log = run_prompt(self.user, "hi", source="playground", priority="balanced")
            Feedback.objects.create(request_log=log, user=self.user, stars=1)
        after = decide("hi", "balanced")
        chosen = log.model_used
        p_before = next(r["p_good"] for r in before.scores if r["model_id"] == chosen)
        p_after = next(r["p_good"] for r in after.scores if r["model_id"] == chosen)
        self.assertLess(p_after, p_before)


@mock.patch("router.llm.complete", side_effect=fake_answer)
class ViewTests(RouterTestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user("admin1", password="pass-12345-x", is_staff=True)
        self.client.force_login(self.user)

    def test_rules_page_and_dry_run(self, complete):
        self.assertEqual(self.client.get(reverse("router:rules")).status_code, 200)
        response = self.client.post(reverse("router:rules"), {"test_prompt": "hi", "priority": "balanced"})
        self.assertContains(response, "Would use")
        complete.assert_not_called()

    def test_only_staff_can_change_rules_and_weights(self, _complete):
        data = {"category": "coding", "keywords": "segfault", "preferred_model": self.models[LARGE].pk, "enabled": "on"}
        self.assertEqual(self.client.post(reverse("router:rule_create"), data).status_code, 403)
        self.assertEqual(self.client.post(reverse("router:settings"), {"quality_weight": 1}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.post(reverse("router:rule_create"), data), reverse("router:rules"))
        rule = RoutingRule.objects.get()
        self.assertEqual(rule.created_by, self.staff)
        self.client.post(reverse("router:rule_delete", args=[rule.pk]))
        self.assertFalse(RoutingRule.objects.exists())

    def test_rule_form_rejects_same_preferred_and_fallback(self, _complete):
        self.client.force_login(self.staff)
        large = self.models[LARGE].pk
        response = self.client.post(reverse("router:rule_create"),
                                    {"category": "coding", "keywords": "x", "preferred_model": large, "fallback_model": large})
        self.assertContains(response, "The fallback must be a different model.")

    def test_staff_can_save_weights(self, _complete):
        self.client.force_login(self.staff)
        data = {"quality_weight": 1.5, "cost_weight": 0.5, "speed_weight": 0, "confidence_threshold": 0.7}
        self.client.post(reverse("router:settings"), data)
        self.assertEqual(RoutingSettings.load().cost_weight, 0.5)

    def test_explain_page_is_private_and_takes_feedback(self, _complete):
        log = run_prompt(self.user, "hi there", source="playground")
        url = reverse("router:explain", args=[log.pk])
        self.assertContains(self.client.get(url), "Why ")
        self.assertRedirects(self.client.post(url, {"stars": 4, "comment": "good"}), url)
        self.assertEqual(log.feedback.stars, 4)
        self.client.post(url, {"stars": 2})
        self.assertEqual(Feedback.objects.get(request_log=log).stars, 2)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_invalid_rating_shows_an_error(self, _complete):
        log = run_prompt(self.user, "hi there", source="playground")
        response = self.client.post(reverse("router:explain", args=[log.pk]), {"stars": 9})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Feedback.objects.exists())

    def test_routed_requests_lists_only_my_requests(self, _complete):
        run_prompt(self.user, "my prompt", source="playground")
        run_prompt(self.staff, "someone else's prompt", source="playground")
        response = self.client.get(reverse("router:requests"))
        self.assertContains(response, "my prompt")
        self.assertNotContains(response, "someone else")


class PreviewAPITests(RouterTestCase):
    def post(self, body, **headers):
        return self.client.post(reverse("router:api_preview"), json.dumps(body), content_type="application/json", **headers)

    def test_requires_auth(self):
        self.assertEqual(self.post({"prompt": "hi"}).status_code, 401)

    def test_api_key_returns_the_decision_without_calling_a_model(self):
        _, raw = APIKey.generate(self.user, "test")
        with mock.patch("router.llm.complete") as complete:
            response = self.post({"prompt": "hi", "priority": "cheapest"}, HTTP_AUTHORIZATION=f"Bearer {raw}")
        complete.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["model"], self.models)
        self.assertEqual(len(response.json()["fallback_order"]), 2)

    def test_rejects_bad_input(self):
        self.client.force_login(self.user)
        self.assertEqual(self.post({"prompt": ""}).status_code, 400)
        self.assertEqual(self.post({"prompt": "hi", "priority": "turbo"}).status_code, 400)
