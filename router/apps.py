from django.apps import AppConfig


class RouterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "router"
    verbose_name = "Smart Router"

    def ready(self):
        from . import signals  # noqa: F401  (connects the RequestLog post_save handler)
