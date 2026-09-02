from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from .activity import log_activity
from .login_throttle import (
    is_locked_out,
    lockout_message,
    register_failure,
    reset as reset_login_failures,
)
from .models import LoginSession
from .network_security import get_request_ip
from .portal_access import (
    is_admin_path,
    is_admin_user,
    is_bde_user,
)


def default_workspace_redirect(user):
    if is_admin_user(user):
        return "dashboard:admin_overview"

    return "dashboard:home"


def _make_form(request):
    if request.method == "POST":
        return AuthenticationForm(
            request=request,
            data=request.POST,
        )

    return AuthenticationForm(request=request)


def _attempted_username(request):
    return str(
        request.POST.get("username", "")
    ).strip()


def _reject_locked_out(request, form):
    """Add the lockout error to `form` and log it. True when locked out."""

    username = _attempted_username(request)

    if not is_locked_out(request, username):
        return False

    form.add_error(None, lockout_message())

    log_activity(
        request,
        "LOGIN_BLOCKED",
        "Sign-in blocked: too many failed attempts.",
        metadata={"username": username},
    )

    return True


def _record_failed_attempt(request):
    """Count a failed sign-in and log it for the audit trail."""

    username = _attempted_username(request)

    count = register_failure(request, username)

    log_activity(
        request,
        "LOGIN_FAILED",
        "Sign-in failed: invalid credentials.",
        metadata={
            "username": username,
            "failed_attempts": count,
        },
    )


def _record_login(request, user):
    login(request, user)

    if not request.session.session_key:
        request.session.save()

    LoginSession.objects.create(
        user=user,
        session_key=request.session.session_key or "",
        ip_address=get_request_ip(request) or None,
        user_agent=request.META.get(
            "HTTP_USER_AGENT",
            "",
        ),
        is_active=True,
    )

    log_activity(
        request,
        "LOGIN",
        "Employee signed in.",
        target_type="user",
        target_id=user.pk,
    )

    messages.success(
        request,
        "Signed in successfully.",
    )


def _safe_admin_next(request):
    next_url = request.GET.get(
        "next",
        "",
    ).strip()

    if not next_url:
        return None

    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None

    next_path = urlsplit(next_url).path

    if not is_admin_path(next_path):
        return None

    if next_path == reverse(
        "accounts:admin_login"
    ):
        return None

    return next_url


@never_cache
@csrf_protect
def login_view(request):
    """BDE-only login page."""

    if request.user.is_authenticated:
        return redirect(
            default_workspace_redirect(
                request.user
            )
        )

    form = _make_form(request)

    if request.method == "POST" and _reject_locked_out(request, form):
        pass

    elif request.method == "POST" and form.is_valid():
        user = form.get_user()

        if not getattr(
            user,
            "is_account_active",
            True,
        ):
            # The password was correct, so this is not a brute-force
            # signal - do not count it against the attempt limit.
            form.add_error(
                None,
                (
                    "This account has been deactivated. "
                    "Contact your administrator."
                ),
            )

        elif not is_bde_user(user):
            form.add_error(
                None,
                (
                    "This is an administrator account. "
                    "Use Admin Center Sign In."
                ),
            )

        else:
            reset_login_failures(
                request,
                _attempted_username(request),
            )

            _record_login(request, user)

            return redirect(
                "dashboard:home"
            )

    elif request.method == "POST":
        _record_failed_attempt(request)

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
        },
    )


@never_cache
@csrf_protect
def admin_login_view(request):
    """Admin-only login page."""

    if request.user.is_authenticated:
        if is_admin_user(request.user):
            return redirect(
                "dashboard:admin_overview"
            )

        return render(
            request,
            "dashboard/access_denied.html",
            {
                "requested_area": "Admin Center",
            },
            status=403,
        )

    form = _make_form(request)

    if request.method == "POST" and _reject_locked_out(request, form):
        pass

    elif request.method == "POST" and form.is_valid():
        user = form.get_user()

        if not getattr(
            user,
            "is_account_active",
            True,
        ):
            # The password was correct, so this is not a brute-force
            # signal - do not count it against the attempt limit.
            form.add_error(
                None,
                (
                    "This account has been deactivated. "
                    "Contact your administrator."
                ),
            )

        elif not is_admin_user(user):
            form.add_error(
                None,
                (
                    "This is a BDE account. "
                    "Use BDE Workspace Sign In."
                ),
            )

        else:
            reset_login_failures(
                request,
                _attempted_username(request),
            )

            _record_login(request, user)

            destination = _safe_admin_next(
                request
            )

            if destination:
                return redirect(destination)

            return redirect(
                "dashboard:admin_overview"
            )

    elif request.method == "POST":
        _record_failed_attempt(request)

    return render(
        request,
        "accounts/admin_login.html",
        {
            "form": form,
        },
    )


@require_POST
def logout_view(request):
    requested_destination = request.POST.get(
        "destination",
        "",
    ).strip()

    signed_in_as_admin = is_admin_user(
        request.user
    )

    if request.user.is_authenticated:
        session_key = request.session.session_key

        if session_key:
            LoginSession.objects.filter(
                user=request.user,
                session_key=session_key,
                is_active=True,
            ).update(
                is_active=False,
                logout_at=timezone.now(),
            )

        log_activity(
            request,
            "LOGOUT",
            "Employee signed out.",
            target_type="user",
            target_id=request.user.pk,
        )

    logout(request)

    if requested_destination == "admin":
        return redirect(
            "accounts:admin_login"
        )

    if requested_destination == "bde":
        return redirect(
            "accounts:login"
        )

    if signed_in_as_admin:
        return redirect(
            "accounts:admin_login"
        )

    return redirect(
        "accounts:login"
    )


@login_required
@require_POST
def session_location_update(request):
    import json
    from decimal import Decimal, InvalidOperation

    try:
        payload = json.loads(request.body.decode("utf-8"))

        latitude = Decimal(str(payload.get("latitude")))
        longitude = Decimal(str(payload.get("longitude")))
        accuracy = float(payload.get("accuracy"))

    except (TypeError, ValueError, InvalidOperation, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "error": "Invalid location data"},
            status=400
        )

    if not (-90 <= latitude <= 90):
        return JsonResponse(
            {"ok": False, "error": "Invalid latitude"},
            status=400
        )

    if not (-180 <= longitude <= 180):
        return JsonResponse(
            {"ok": False, "error": "Invalid longitude"},
            status=400
        )

    if accuracy < 0:
        return JsonResponse(
            {"ok": False, "error": "Invalid accuracy"},
            status=400
        )

    session_key = request.session.session_key

    if not session_key:
        return JsonResponse(
            {"ok": False, "error": "No active session"},
            status=400
        )

    login_session = (
        LoginSession.objects
        .filter(
            user=request.user,
            session_key=session_key,
            is_active=True
        )
        .order_by("-login_at")
        .first()
    )

    if not login_session:
        return JsonResponse(
            {"ok": False, "error": "Login session not found"},
            status=404
        )

    login_session.latitude = latitude
    login_session.longitude = longitude
    login_session.location_accuracy = accuracy

    login_session.save(
        update_fields=[
            "latitude",
            "longitude",
            "location_accuracy",
        ]
    )

    return JsonResponse({"ok": True})
