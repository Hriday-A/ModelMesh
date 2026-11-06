import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from accounts.models import APIKey, UserProfile
from accounts.services import ProviderError

from .forms import FeedbackForm, RoutingRuleForm, RoutingSettingsForm, TestPromptForm
from .models import RouterModel, RoutingRule, RoutingSettings
from .services import decide

PRIORITIES = dict(UserProfile.PRIORITY_CHOICES)


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only staff can change routing. Logged-in non-staff users get a 403."""

    raise_exception = False

    def test_func(self):
        return self.request.user.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            self.raise_exception = True
        return super().handle_no_permission()


def score_rows(scores, chosen_id):
    """Rows for the score table, in model-tier order. scores: list or {model_id: row}."""
    rows = list(scores.values()) if isinstance(scores, dict) else list(scores)
    models = {m.model_id: m for m in RouterModel.objects.filter(model_id__in=[r["model_id"] for r in rows])}
    table = []
    for row in rows:
        model = models.get(row["model_id"])
        table.append({
            **row,
            "name": model.name if model else row["model_id"],
            "tier": model.tier if model else 0,
            "p_good_pct": None if row["p_good"] is None else round(row["p_good"] * 100),
            "chosen": row["model_id"] == chosen_id,
        })
    return sorted(table, key=lambda r: r["tier"])


class RoutingRulesView(LoginRequiredMixin, TemplateView):
    """Screen 11: rules, score weights and a dry-run test prompt."""

    template_name = "router/rules.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rules = list(RoutingRule.objects.select_related("preferred_model", "fallback_model"))
        for rule in rules:
            rule.score_avg, rule.score_n = rule.learned_score()
        context["rules"] = rules
        context["models"] = RouterModel.objects.all()
        context["can_edit"] = self.request.user.is_staff
        context.setdefault("settings_form", RoutingSettingsForm(instance=RoutingSettings.load()))
        context.setdefault("test_form", TestPromptForm(initial={"priority": self.request.user.profile.default_priority}))
        return context

    def post(self, request, *args, **kwargs):
        """Try a test prompt: shows which model would be picked, without sending it."""
        form = TestPromptForm(request.POST)
        context = {"test_form": form}
        if form.is_valid():
            try:
                decision = decide(form.cleaned_data["test_prompt"], form.cleaned_data["priority"])
            except ProviderError as e:
                form.add_error(None, str(e))
            else:
                chosen = decision.order[0]
                context["test_result"] = {
                    "chosen": chosen,
                    "reason": decision.reason(chosen),
                    "rows": score_rows(decision.scores, chosen.model_id),
                    "classifier_used": decision.classifier_used,
                }
        return self.render_to_response(self.get_context_data(**context))


class RoutingSettingsUpdateView(StaffRequiredMixin, UpdateView):
    form_class = RoutingSettingsForm
    template_name = "router/rules.html"
    success_url = reverse_lazy("router:rules")
    http_method_names = ["post"]

    def get_object(self, queryset=None):
        return RoutingSettings.load()

    def form_valid(self, form):
        messages.success(self.request, "Score weights saved.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Weights not saved: " + "; ".join(e for errs in form.errors.values() for e in errs))
        return redirect("router:rules")


class RuleCreateView(StaffRequiredMixin, CreateView):
    model = RoutingRule
    form_class = RoutingRuleForm
    template_name = "router/rule_form.html"
    success_url = reverse_lazy("router:rules")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Rule created.")
        return super().form_valid(form)


class RuleUpdateView(StaffRequiredMixin, UpdateView):
    model = RoutingRule
    form_class = RoutingRuleForm
    template_name = "router/rule_form.html"
    success_url = reverse_lazy("router:rules")

    def form_valid(self, form):
        messages.success(self.request, "Rule saved.")
        return super().form_valid(form)


class RuleDeleteView(StaffRequiredMixin, DeleteView):
    model = RoutingRule
    template_name = "router/rule_confirm_delete.html"
    success_url = reverse_lazy("router:rules")

    def form_valid(self, form):
        messages.info(self.request, "Rule deleted.")
        return super().form_valid(form)


class RoutedRequestsView(LoginRequiredMixin, ListView):
    """The user's requests that went through the smart router."""

    template_name = "router/requests.html"
    context_object_name = "logs"
    paginate_by = 20

    def get_queryset(self):
        return (
            self.request.user.request_logs.filter(routing_decision__isnull=False)
            .select_related("routing_decision__chosen_model", "feedback")
        )


class ExplainView(LoginRequiredMixin, View):
    """Screen 12: why a model was chosen for one request, plus star feedback."""

    template_name = "router/explain.html"

    def get_log(self, request, log_id):
        # Only the owner can see a request: others get a 404.
        return get_object_or_404(request.user.request_logs.select_related("routing_decision"), pk=log_id)

    def context(self, log, form=None):
        decision = getattr(log, "routing_decision", None)
        existing = getattr(log, "feedback", None)
        return {
            "log": log,
            "decision": decision,
            "rows": score_rows(decision.scores, decision.chosen_model.model_id if decision.chosen_model else None)
            if decision else [],
            "feedback": existing,
            "form": form or FeedbackForm(instance=existing),
        }

    def get(self, request, log_id):
        return render(request, self.template_name, self.context(self.get_log(request, log_id)))

    def post(self, request, log_id):
        log = self.get_log(request, log_id)
        if log.status == "error":
            messages.error(request, "Failed requests can't be rated.")
            return redirect("router:explain", log_id=log.pk)
        form = FeedbackForm(request.POST, instance=getattr(log, "feedback", None))
        if not form.is_valid():
            return render(request, self.template_name, self.context(log, form))
        feedback = form.save(commit=False)
        feedback.request_log = log
        feedback.user = request.user
        feedback.save()
        messages.success(request, "Thanks! Your rating will help the router choose better.")
        return redirect("router:explain", log_id=log.pk)


@method_decorator(csrf_exempt, name="dispatch")
class PreviewAPIView(View):
    """POST /routing/api/preview — which model would answer, without calling it.

    Auth: a logged-in session or "Authorization: Bearer mm_...". It changes nothing,
    so it is CSRF-exempt like /api/chat.
    Body: {"prompt": "...", "priority": "balanced"}
    """

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        if user is None:
            api_key = APIKey.authenticate(request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
            user = api_key.user if api_key else None
        if user is None:
            return JsonResponse({"error": "Log in or send a valid API key."}, status=401)

        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Request body must be JSON."}, status=400)
        if not isinstance(body, dict):
            return JsonResponse({"error": "Request body must be a JSON object."}, status=400)
        prompt = str(body.get("prompt", "")).strip()
        priority = body.get("priority") or user.profile.default_priority
        if not prompt or len(prompt) > 20000:
            return JsonResponse({"error": "prompt is required (max 20,000 characters)."}, status=400)
        if priority not in PRIORITIES:
            return JsonResponse({"error": f"priority must be one of {', '.join(PRIORITIES)}."}, status=400)

        try:
            decision = decide(prompt, priority)
        except ProviderError as e:
            return JsonResponse({"error": str(e)}, status=503)
        chosen = decision.order[0]
        return JsonResponse({
            "model": chosen.model_id,
            "fallback_order": [m.model_id for m in decision.order[1:]],
            "category": decision.category,
            "classifier": decision.classifier_used,
            "reason": decision.reason(chosen),
            "scores": decision.scores,
        })

    def get(self, request):
        return JsonResponse({"error": "Use POST."}, status=405)
