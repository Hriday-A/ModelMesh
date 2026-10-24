import json

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from .forms import APIKeyForm, HistoryFilterForm, PlaygroundForm, ProfileForm, SignUpForm
from .models import APIKey, RequestLog
from .services import run_prompt


class HomeView(TemplateView):
    template_name = "accounts/home.html"


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("accounts:playground")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, "Welcome to ModelMesh! Try your first prompt below.")
        return response


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        return self.request.user.profile

    def form_valid(self, form):
        messages.success(self.request, "Profile saved.")
        return super().form_valid(form)


class APIKeyListView(LoginRequiredMixin, ListView):
    template_name = "accounts/api_keys.html"
    context_object_name = "api_keys"

    def get_queryset(self):
        return self.request.user.api_keys.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or APIKeyForm(user=self.request.user)
        # The full key is shown once, right after it is created, then forgotten.
        context["new_raw_key"] = self.request.session.pop("new_raw_key", None)
        return context

    def post(self, request, *args, **kwargs):
        form = APIKeyForm(request.POST, user=request.user)
        if form.is_valid():
            _, raw_key = APIKey.generate(request.user, form.cleaned_data["name"])
            request.session["new_raw_key"] = raw_key
            return redirect("accounts:api_keys")
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class APIKeyRevokeView(LoginRequiredMixin, View):
    def post(self, request, pk):
        api_key = get_object_or_404(APIKey, pk=pk, user=request.user)
        api_key.revoked = True
        api_key.save(update_fields=["revoked"])
        messages.info(request, f"Key “{api_key.name}” was revoked.")
        return redirect("accounts:api_keys")


class PlaygroundView(LoginRequiredMixin, FormView):
    form_class = PlaygroundForm
    template_name = "accounts/playground.html"

    def get_initial(self):
        return {"priority": self.request.user.profile.default_priority}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recent_logs"] = self.request.user.request_logs.all()[:5]
        return context

    def form_valid(self, form):
        log = run_prompt(
            user=self.request.user,
            prompt=form.cleaned_data["prompt"],
            source="playground",
            priority=form.cleaned_data["priority"],
        )
        return self.render_to_response(self.get_context_data(form=form, result=log))


class RequestHistoryView(LoginRequiredMixin, ListView):
    template_name = "accounts/history.html"
    context_object_name = "logs"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = HistoryFilterForm(self.request.GET or None)
        return self.filter_form.filter(self.request.user.request_logs.all())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        # Keep filters when moving between pages.
        params = self.request.GET.copy()
        params.pop("page", None)
        context["filter_query"] = params.urlencode()
        return context


class RequestDetailView(LoginRequiredMixin, DetailView):
    template_name = "accounts/request_detail.html"
    context_object_name = "log"

    def get_queryset(self):
        return self.request.user.request_logs.all()


@method_decorator(csrf_exempt, name="dispatch")
class ChatAPIView(View):
    """POST /api/chat — the entry point programs use.

    Header:  Authorization: Bearer mm_...
    Body:    {"prompt": "...", "priority": "balanced"}   (priority optional)
    """

    def post(self, request):
        auth = request.headers.get("Authorization", "")
        api_key = APIKey.authenticate(auth.removeprefix("Bearer ").strip())
        if api_key is None:
            return JsonResponse({"error": "Missing, invalid or revoked API key."}, status=401)

        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Request body must be JSON."}, status=400)
        if not isinstance(body, dict):
            return JsonResponse({"error": "Request body must be a JSON object."}, status=400)

        form = PlaygroundForm({
            "prompt": body.get("prompt", ""),
            "priority": body.get("priority") or api_key.user.profile.default_priority,
        })
        if not form.is_valid():
            return JsonResponse({"error": "Invalid request.", "details": form.errors}, status=400)

        log = run_prompt(
            user=api_key.user,
            prompt=form.cleaned_data["prompt"],
            source="api",
            priority=form.cleaned_data["priority"],
            api_key=api_key,
        )
        if log.status == "error":
            return JsonResponse({"id": log.id, "error": log.error_message}, status=502)
        return JsonResponse({
            "id": log.id,
            "response": log.response,
            "model": log.model_used,
            "provider": log.provider,
            "routing_reason": log.routing_reason,
            "cached": log.status == "cached",
            "usage": {"input_tokens": log.input_tokens, "output_tokens": log.output_tokens},
            "cost_usd": str(log.cost_usd),
            "latency_ms": log.latency_ms,
        })

    def get(self, request):
        return JsonResponse({"error": "Use POST."}, status=405)
