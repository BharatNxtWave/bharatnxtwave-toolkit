from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from .health import healthz

urlpatterns = [
    # Exempt from the office IP allow-list; see config/health.py.
    path(settings.HEALTH_CHECK_PATH.lstrip("/"), healthz, name="healthz"),
]

# Django's built-in admin. Its path is configurable, and setting
# BHARATNXT_DJANGO_ADMIN_PATH to an empty string removes it entirely.
# See the DJANGO_ADMIN_PATH notes in config/settings.py.
if settings.DJANGO_ADMIN_PATH:
    urlpatterns.append(
        path(settings.DJANGO_ADMIN_PATH, admin.site.urls)
    )

urlpatterns += [
    path("", include("dashboard.urls")),
    path("", include("accounts.urls")),
    path("", include("toolkit.urls")),
]
