"""Liveness endpoint for the hosting platform.

Render polls this to decide whether a deploy succeeded and whether the
service is still up. The poll comes from inside the platform's network, not
from the office, so OfficeNetworkMiddleware has to let it through - see
HEALTH_CHECK_PATH in settings and the exemption in
accounts/network_security.py.

It deliberately returns nothing but "ok". The response is reachable without
authentication and from outside the office allow-list, so it must not expose
version numbers, settings, database state or anything else about the system.
"""

from django.http import HttpResponse


def healthz(request):
    return HttpResponse(
        "ok",
        content_type="text/plain",
    )
