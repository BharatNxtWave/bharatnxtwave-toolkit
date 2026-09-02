"""Tests for client-IP resolution behind a proxy, and the health exemption.

This is the input to the office-network allow-list, so a mistake here either
locks the whole office out or makes the allow-list trivially spoofable by
sending an X-Forwarded-For header.
"""

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from accounts.network_security import (
    OfficeNetworkMiddleware,
    get_request_ip,
)


OFFICE_PUBLIC_IP = "203.0.113.5"
ATTACKER_IP = "198.51.100.9"


class ForwardedModeTests(SimpleTestCase):
    """PROXY_MODE='forwarded' - managed platforms such as Render."""

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, forwarded_for=None, remote_addr="10.0.0.7"):
        headers = {"REMOTE_ADDR": remote_addr}

        if forwarded_for is not None:
            headers["HTTP_X_FORWARDED_FOR"] = forwarded_for

        return self.factory.get("/", **headers)

    @override_settings(PROXY_MODE="forwarded", TRUSTED_PROXY_HOPS=1)
    def test_single_entry_is_the_client(self):
        request = self._request(OFFICE_PUBLIC_IP)

        self.assertEqual(get_request_ip(request), OFFICE_PUBLIC_IP)

    @override_settings(PROXY_MODE="forwarded", TRUSTED_PROXY_HOPS=1)
    def test_client_supplied_header_cannot_spoof_the_office_ip(self):
        """The security case.

        An attacker sends their own X-Forwarded-For claiming to be the
        office. The platform appends the address it actually saw, so the
        spoofed value ends up on the LEFT and the real one on the right.
        Reading from the right must ignore the spoof.
        """

        request = self._request(f"{OFFICE_PUBLIC_IP}, {ATTACKER_IP}")

        self.assertEqual(get_request_ip(request), ATTACKER_IP)

    @override_settings(PROXY_MODE="forwarded", TRUSTED_PROXY_HOPS=2)
    def test_two_hops_reads_one_further_left(self):
        request = self._request(
            f"{ATTACKER_IP}, {OFFICE_PUBLIC_IP}, 10.0.0.1"
        )

        self.assertEqual(get_request_ip(request), OFFICE_PUBLIC_IP)

    @override_settings(PROXY_MODE="forwarded", TRUSTED_PROXY_HOPS=9)
    def test_hops_cannot_walk_past_the_left_edge(self):
        """An over-large hop count must not fall off the list."""

        request = self._request(f"{ATTACKER_IP}, {OFFICE_PUBLIC_IP}")

        self.assertEqual(get_request_ip(request), ATTACKER_IP)

    @override_settings(PROXY_MODE="forwarded", TRUSTED_PROXY_HOPS=1)
    def test_missing_header_falls_back_to_remote_addr(self):
        request = self._request(None, remote_addr="10.0.0.7")

        self.assertEqual(get_request_ip(request), "10.0.0.7")

    @override_settings(PROXY_MODE="forwarded", TRUSTED_PROXY_HOPS=1)
    def test_garbage_header_does_not_yield_a_bogus_ip(self):
        request = self._request("not-an-ip", remote_addr="10.0.0.7")

        self.assertEqual(get_request_ip(request), "10.0.0.7")


class XRealIpModeTests(SimpleTestCase):
    """PROXY_MODE='xrealip' - the self-hosted nginx default."""

    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(
        PROXY_MODE="xrealip",
        TRUSTED_PROXY_IPS=["127.0.0.1"],
    )
    def test_x_real_ip_is_honoured_from_the_trusted_proxy(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_REAL_IP=OFFICE_PUBLIC_IP,
        )

        self.assertEqual(get_request_ip(request), OFFICE_PUBLIC_IP)

    @override_settings(
        PROXY_MODE="xrealip",
        TRUSTED_PROXY_IPS=["127.0.0.1"],
    )
    def test_x_real_ip_is_ignored_from_an_untrusted_peer(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR=ATTACKER_IP,
            HTTP_X_REAL_IP=OFFICE_PUBLIC_IP,
        )

        self.assertEqual(get_request_ip(request), ATTACKER_IP)

    @override_settings(
        PROXY_MODE="xrealip",
        TRUSTED_PROXY_IPS=["127.0.0.1"],
    )
    def test_forwarded_for_is_ignored_in_this_mode(self):
        """X-Forwarded-For must not be honoured when nginx sets X-Real-IP."""

        request = self.factory.get(
            "/",
            REMOTE_ADDR=ATTACKER_IP,
            HTTP_X_FORWARDED_FOR=OFFICE_PUBLIC_IP,
        )

        self.assertEqual(get_request_ip(request), ATTACKER_IP)


@override_settings(
    OFFICE_NETWORK_ENFORCED=True,
    OFFICE_ALLOWED_NETWORKS=[f"{OFFICE_PUBLIC_IP}/32"],
    PROXY_MODE="forwarded",
    TRUSTED_PROXY_HOPS=1,
    HEALTH_CHECK_PATH="/healthz/",
)
class OfficeNetworkMiddlewareTests(SimpleTestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = OfficeNetworkMiddleware(
            lambda request: HttpResponse("reached")
        )

    def _get(self, path, forwarded_for):
        request = self.factory.get(
            path,
            REMOTE_ADDR="10.0.0.7",
            HTTP_X_FORWARDED_FOR=forwarded_for,
        )

        return self.middleware(request)

    def test_office_ip_is_allowed(self):
        response = self._get("/", OFFICE_PUBLIC_IP)

        self.assertEqual(response.status_code, 200)

    def test_other_ip_is_blocked(self):
        response = self._get("/", ATTACKER_IP)

        self.assertEqual(response.status_code, 403)

    def test_spoofed_forwarded_header_is_still_blocked(self):
        """Claiming to be the office from outside must not work."""

        response = self._get("/", f"{OFFICE_PUBLIC_IP}, {ATTACKER_IP}")

        self.assertEqual(response.status_code, 403)

    def test_health_check_is_exempt(self):
        """Render polls this from its own network; it must not 403."""

        response = self._get("/healthz/", ATTACKER_IP)

        self.assertEqual(response.status_code, 200)

    def test_health_exemption_does_not_leak_to_other_paths(self):
        response = self._get("/healthz/../", ATTACKER_IP)

        self.assertEqual(response.status_code, 403)
