import ipaddress

from django.conf import settings
from django.http import HttpResponseForbidden


def valid_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except (ValueError, TypeError):
        return False


def _ip_from_x_real_ip(request, remote_addr):
    """Self-hosted nginx: trust X-Real-IP only from our own proxy."""

    trusted_proxies = getattr(
        settings,
        "TRUSTED_PROXY_IPS",
        [
            "127.0.0.1",
            "::1",
        ]
    )

    if remote_addr in trusted_proxies:
        real_ip = request.META.get(
            "HTTP_X_REAL_IP",
            ""
        ).strip()

        if valid_ip(real_ip):
            return real_ip

    return ""


def _ip_from_forwarded_for(request):
    """Managed platform (Render, and other PaaS load balancers).

    On a managed platform REMOTE_ADDR is an internal address of the
    platform's router, so it cannot be matched against a fixed proxy list.
    The client address has to come from X-Forwarded-For instead.

    X-Forwarded-For grows left-to-right: every proxy appends the address it
    received the request from. Anything a client sends arrives at the far
    LEFT, so the leftmost entry is attacker-controlled and must never be
    trusted. Counting `hops` in from the RIGHT lands on the address the
    outermost trusted proxy actually observed.

        client sends:  X-Forwarded-For: 9.9.9.9        (spoofed)
        platform appends the real peer:  9.9.9.9, 203.0.113.5
        hops = 1  ->  203.0.113.5                      (correct)

    Set BHARATNXT_TRUSTED_PROXY_HOPS to the number of proxies the platform
    puts in front of the app - one for Render's load balancer. Setting it
    too high walks into client-supplied territory, so verify it against a
    real request before relying on it (see DEPLOY_RENDER.md).
    """

    forwarded = request.META.get(
        "HTTP_X_FORWARDED_FOR",
        ""
    )

    if not forwarded:
        return ""

    parts = [
        part.strip()
        for part in forwarded.split(",")
        if part.strip()
    ]

    if not parts:
        return ""

    hops = getattr(
        settings,
        "TRUSTED_PROXY_HOPS",
        1,
    )

    try:
        hops = int(hops)
    except (TypeError, ValueError):
        hops = 1

    # Never walk past the left edge into client-supplied entries.
    hops = max(1, min(hops, len(parts)))

    candidate = parts[-hops]

    if valid_ip(candidate):
        return candidate

    return ""


def get_request_ip(request):
    """Resolve the real client IP for the current deployment topology.

    Controlled by BHARATNXT_PROXY_MODE:

      "xrealip"   self-hosted nginx (the default). X-Real-IP is honoured
                  only when REMOTE_ADDR is one of TRUSTED_PROXY_IPS.

      "forwarded" managed platform. The address is read from
                  X-Forwarded-For, counting TRUSTED_PROXY_HOPS in from the
                  right.
    """

    remote_addr = request.META.get(
        "REMOTE_ADDR",
        ""
    )

    mode = str(
        getattr(
            settings,
            "PROXY_MODE",
            "xrealip",
        )
    ).strip().lower()

    if mode == "forwarded":
        forwarded_ip = _ip_from_forwarded_for(request)

        if forwarded_ip:
            return forwarded_ip

    else:
        real_ip = _ip_from_x_real_ip(request, remote_addr)

        if real_ip:
            return real_ip

    if valid_ip(remote_addr):
        return remote_addr

    return ""


class OfficeNetworkMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if not getattr(
            settings,
            "OFFICE_NETWORK_ENFORCED",
            False
        ):
            return self.get_response(request)

        # The hosting platform's health check originates inside the
        # platform network, never from the office, so enforcing the
        # allow-list on it would fail every deploy. The endpoint itself
        # returns nothing but "ok" (see config/health.py).
        health_path = getattr(
            settings,
            "HEALTH_CHECK_PATH",
            "",
        )

        if health_path and request.path_info == health_path:
            return self.get_response(request)

        client_ip = get_request_ip(request)

        if not client_ip:
            return HttpResponseForbidden(
                "Access denied: invalid network address."
            )

        ip = ipaddress.ip_address(
            client_ip
        )

        allowed_networks = getattr(
            settings,
            "OFFICE_ALLOWED_NETWORKS",
            []
        )

        permitted = False

        for network_string in allowed_networks:

            try:
                network = ipaddress.ip_network(
                    network_string,
                    strict=False
                )

            except ValueError:
                continue

            if ip in network:
                permitted = True
                break

        if not permitted:

            try:
                from .activity import log_activity

                log_activity(
                    request,
                    "PERMISSION_DENIED",
                    "Request blocked by office network policy.",
                    metadata={
                        "reason": "outside_office_network",
                        "ip": client_ip,
                    },
                )

            except Exception:
                pass

            return HttpResponseForbidden(
                "This BharatNXT Wave system is available only from the authorised office network."
            )

        return self.get_response(request)
