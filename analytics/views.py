import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView, UpdateView

from .forms import RangeForm, UsageLimitForm
from .models import UsageLimit
from .services import logs_in_range, month_summary, usage_summary


def selected_range(request):
    """The range form and the chosen number of days. Anything invalid falls back to 7."""
    form = RangeForm(request.GET or None)
    days = form.cleaned_data["days"] if form.is_valid() else 7
    return form, days


class UsageDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "analytics/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["range_form"], context["days"] = selected_range(self.request)
        context["summary"] = usage_summary(self.request.user, context["days"])
        return context


class UsageCSVView(LoginRequiredMixin, View):
    """The user's requests in the chosen range as a CSV file. Prompts and answers are left out."""

    COLUMNS = [
        "created_at", "source", "priority", "provider", "model_used", "status",
        "input_tokens", "output_tokens", "cost_usd", "latency_ms",
    ]

    def get(self, request):
        _, days = selected_range(request)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="modelmesh-usage-last-{days}-days.csv"'
        writer = csv.writer(response)
        writer.writerow(self.COLUMNS)
        writer.writerows(logs_in_range(request.user, days).values_list(*self.COLUMNS))
        return response


class UsageLimitView(LoginRequiredMixin, UpdateView):
    form_class = UsageLimitForm
    template_name = "analytics/limits.html"
    success_url = reverse_lazy("analytics:limits")

    def get_object(self, queryset=None):
        usage_limit, _ = UsageLimit.objects.get_or_create(user=self.request.user)
        # The form copies submitted values onto the object before checking them,
        # so keep the saved budget for the "This month" box.
        self.saved_budget = usage_limit.monthly_budget_usd
        return usage_limit

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["month"] = month_summary(self.request.user, self.saved_budget)
        return context

    def form_valid(self, form):
        messages.success(self.request, "Settings saved.")
        return super().form_valid(form)
