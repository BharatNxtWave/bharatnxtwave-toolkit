"""Behavioural tests for login brute-force protection.

Both login forms previously accepted unlimited password attempts. These tests
drive the real views through the test client, so they fail if the throttle is
removed or silently stops counting.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import ActivityLog


User = get_user_model()


@override_settings(
    LOGIN_MAX_FAILED_ATTEMPTS=3,
    LOGIN_LOCKOUT_SECONDS=600,
)
class LoginThrottleTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.password = "correct-horse-battery-4821"

        cls.bde = User.objects.create_user(
            username="throttle_bde",
            password=cls.password,
            role="BDE",
        )

        cls.admin = User.objects.create_user(
            username="throttle_admin",
            password=cls.password,
            role="DATA_ADMIN",
        )

    def setUp(self):
        # Counters live in the cache and would otherwise leak between tests.
        cache.clear()

        self.login_url = reverse("accounts:login")
        self.admin_login_url = reverse("accounts:admin_login")

    def _attempt(self, url, username, password):
        return self.client.post(
            url,
            {"username": username, "password": password},
        )

    def _form_errors(self, response):
        form = response.context["form"]

        return " ".join(form.non_field_errors())

    # -- counting ------------------------------------------------------------

    def test_wrong_password_does_not_sign_in(self):
        response = self._attempt(
            self.login_url,
            "throttle_bde",
            "wrong-password",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.wsgi_request.user.is_authenticated
        )

    def test_lockout_after_the_configured_number_of_failures(self):
        for _ in range(3):
            self._attempt(
                self.login_url,
                "throttle_bde",
                "wrong-password",
            )

        response = self._attempt(
            self.login_url,
            "throttle_bde",
            "wrong-password",
        )

        self.assertIn(
            "Too many failed sign-in attempts",
            self._form_errors(response),
        )

    def test_lockout_rejects_even_the_correct_password(self):
        """A lockout that the real password bypasses is not a lockout."""

        for _ in range(3):
            self._attempt(
                self.login_url,
                "throttle_bde",
                "wrong-password",
            )

        response = self._attempt(
            self.login_url,
            "throttle_bde",
            self.password,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.wsgi_request.user.is_authenticated
        )
        self.assertIn(
            "Too many failed sign-in attempts",
            self._form_errors(response),
        )

    def test_successful_sign_in_clears_the_counter(self):
        for _ in range(2):
            self._attempt(
                self.login_url,
                "throttle_bde",
                "wrong-password",
            )

        signed_in = self._attempt(
            self.login_url,
            "throttle_bde",
            self.password,
        )
        self.assertEqual(signed_in.status_code, 302)

        self.client.logout()

        # The two earlier failures must not carry over.
        for _ in range(2):
            response = self._attempt(
                self.login_url,
                "throttle_bde",
                "wrong-password",
            )

        self.assertNotIn(
            "Too many failed sign-in attempts",
            self._form_errors(response),
        )

    # -- scope ---------------------------------------------------------------

    def test_admin_login_is_throttled_too(self):
        for _ in range(3):
            self._attempt(
                self.admin_login_url,
                "throttle_admin",
                "wrong-password",
            )

        response = self._attempt(
            self.admin_login_url,
            "throttle_admin",
            "wrong-password",
        )

        self.assertIn(
            "Too many failed sign-in attempts",
            self._form_errors(response),
        )

    def test_wrong_portal_does_not_count_as_a_failure(self):
        """A BDE using the admin form supplied a valid password.

        Counting it would let ordinary user error lock people out.
        """

        for _ in range(4):
            response = self._attempt(
                self.admin_login_url,
                "throttle_bde",
                self.password,
            )

        self.assertIn(
            "This is a BDE account",
            self._form_errors(response),
        )
        self.assertNotIn(
            "Too many failed sign-in attempts",
            self._form_errors(response),
        )

    # -- audit trail ---------------------------------------------------------

    def test_failed_attempts_are_logged(self):
        self._attempt(
            self.login_url,
            "throttle_bde",
            "wrong-password",
        )

        self.assertTrue(
            ActivityLog.objects.filter(
                action="LOGIN_FAILED"
            ).exists()
        )

    def test_blocked_attempts_are_logged(self):
        for _ in range(4):
            self._attempt(
                self.login_url,
                "throttle_bde",
                "wrong-password",
            )

        self.assertTrue(
            ActivityLog.objects.filter(
                action="LOGIN_BLOCKED"
            ).exists()
        )
