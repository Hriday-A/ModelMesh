from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from .forms import AIModelFormSet, ProviderForm
from .models import Provider
from .services import check_health, recent_stats


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class ProviderListView(LoginRequiredMixin, ListView):
    """Screen 9: providers, their models and health."""

    template_name = "providers/provider_list.html"
    context_object_name = "providers"

    def get_queryset(self):
        return Provider.objects.prefetch_related("models")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stats = recent_stats()
        for provider in context["providers"]:
            provider.stats = stats.get(provider.slug)
        return context


class ProviderFormView(StaffRequiredMixin, View):
    """Screen 10: add or edit a provider and its models on one page."""

    template_name = "providers/provider_form.html"

    def render_form(self, request, provider, form, formset):
        return render(request, self.template_name, {"provider": provider, "form": form, "formset": formset})

    def get(self, request, pk=None):
        provider = get_object_or_404(Provider, pk=pk) if pk else None
        return self.render_form(
            request, provider, ProviderForm(instance=provider), AIModelFormSet(instance=provider, prefix="models")
        )

    def post(self, request, pk=None):
        provider = get_object_or_404(Provider, pk=pk) if pk else None
        form = ProviderForm(request.POST, instance=provider)
        formset = AIModelFormSet(request.POST, instance=provider, prefix="models")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                saved = form.save()
                formset.instance = saved
                formset.save()
            messages.success(request, f"Saved {saved.name}.")
            return redirect("providers:list")
        messages.error(request, "Some fields need fixing. Each problem is shown next to its field.")
        return self.render_form(request, provider, form, formset)


class ProviderHealthCheckView(StaffRequiredMixin, View):
    def post(self, request, pk):
        provider = get_object_or_404(Provider, pk=pk)
        check_health(provider)
        messages.success(
            request, f"{provider.name}: {provider.get_health_status_display()}. {provider.health_detail}"
        )
        return redirect(reverse("providers:list") + f"#provider-{provider.pk}")
