"""Brute-force protection for the two login forms.

Both login views previously accepted unlimited password attempts: no counter,
no lockout, no delay. The office-network middleware narrows who can reach the
form, but it does nothing against an attacker who is already on the LAN or VPN,
or against a compromised office machine.

Failures are counted twice - once per username and once per client IP - so that
both a single account under attack and a single machine spraying many usernames
get locked out.

The counters live in Django's cache. In production that must be a cache shared
by every gunicorn worker (see CACHES in config/settings.py); a per-process cache
would multiply the effective attempt limit by the worker count.
"""

from django.conf import settings
from django.core.cache import cache

from .network_security import get_request_ip


CACHE_PREFIX = "login-throttle"


def _max_attempts():
    return getattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 5)


def _lockout_seconds():
    return getattr(settings, "LOGIN_LOCKOUT_SECONDS", 15 * 60)


def _keys(request, username):
    """Cache keys for this attempt: one per account, one per client IP."""

    keys = []

    name = str(username or "").strip().lower()

    if name:
        keys.append(f"{CACHE_PREFIX}:user:{name}")

    ip = get_request_ip(request)

    if ip:
        keys.append(f"{CACHE_PREFIX}:ip:{ip}")

    return keys


def is_locked_out(request, username):
    """True when either counter has reached the limit."""

    limit = _max_attempts()

    for key in _keys(request, username):
        if cache.get(key, 0) >= limit:
            return True

    return False


def register_failure(request, username):
    """Count a failed attempt. Returns the highest counter after counting."""

    timeout = _lockout_seconds()
    highest = 0

    for key in _keys(request, username):
        # add() only sets the key when it is absent, which starts the window;
        # incr() then counts within that same window so the expiry is not
        # pushed back by every new attempt.
        cache.add(key, 0, timeout)

        try:
            count = cache.incr(key)
        except ValueError:
            # The key expired between add() and incr().
            cache.set(key, 1, timeout)
            count = 1

        highest = max(highest, count)

    return highest


def reset(request, username):
    """Clear the counters after a successful sign-in."""

    for key in _keys(request, username):
        cache.delete(key)


def lockout_message():
    minutes = max(1, _lockout_seconds() // 60)

    return (
        "Too many failed sign-in attempts. "
        f"Try again in {minutes} minutes, "
        "or contact your administrator."
    )
