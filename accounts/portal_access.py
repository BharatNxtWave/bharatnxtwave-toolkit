from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse


ADMIN_ROLES = frozenset(
    {
        "SUPER_ADMIN",
        "IT_ADMIN",
        "DATA_ADMIN",
        "SECURITY_ADMIN",
    }
)


ADMIN_PROTECTED_PREFIXES = (
    "/admin-center/",
    "/employees/",
    "/activity-logs/",
)


def admin_protected_prefixes():
    """Protected prefixes, including Django's built-in admin.

    The built-in admin gives direct model access, so it is gated by the same
    role rules as the Admin Centre rather than by Django's `is_staff` flag
    alone. Its path is configurable - see DJANGO_ADMIN_PATH in settings.
    """

    prefixes = list(ADMIN_PROTECTED_PREFIXES)

    django_admin = getattr(
        settings,
        "DJANGO_ADMIN_PATH",
        "",
    )

    if django_admin:
        prefixes.append(f"/{django_admin.strip('/')}/")

    return tuple(prefixes)


def is_admin_user(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or getattr(user, "role", "") in ADMIN_ROLES
        )
    )


def is_bde_user(user):
    return bool(
        user
        and user.is_authenticated
        and not is_admin_user(user)
        and getattr(user, "role", "") == "BDE"
    )


def is_admin_path(path):
    return any(
        (path or "").startswith(prefix)
        for prefix in admin_protected_prefixes()
    )


class AdminPortalAccessMiddleware:
    """Protect every custom Admin Center route."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or "/"
        admin_login_path = reverse(
            "accounts:admin_login"
        )

        if path == admin_login_path:
            return self.get_response(request)

        if not is_admin_path(path):
            return self.get_response(request)

        if not request.user.is_authenticated:
            query = urlencode(
                {"next": request.get_full_path()}
            )

            return redirect(
                f"{admin_login_path}?{query}"
            )

        if not is_admin_user(request.user):
            return render(
                request,
                "dashboard/access_denied.html",
                {
                    "requested_area": "Admin Center",
                },
                status=403,
            )

        return self.get_response(request)
