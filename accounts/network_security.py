import ipaddress

from django.conf import settings
from django.http import HttpResponseForbidden


def valid_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except (ValueError, TypeError):
        return False


def get_request_ip(request):
    """
    Resolve the real client IP safely.

    X-Real-IP is trusted only when the request comes from
    our explicitly trusted local reverse proxy.
    """

    remote_addr = request.META.get(
        "REMOTE_ADDR",
        ""
    )

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
