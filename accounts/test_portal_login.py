from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import LoginSession


class SplitPortalAuthenticationTests(TestCase):
    password = "Temporary-Test-Password-2026!"

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.bde = User.objects.create_user(
            username="portal.test.bde",
            password=cls.password,
            employee_id="BNXT-PORTAL-BDE-001",
            role="BDE",
            is_active=True,
            is_account_active=True,
        )

        cls.admin = User.objects.create_user(
            username="portal.test.admin",
            password=cls.password,
            employee_id="BNXT-PORTAL-ADMIN-001",
            role="SUPER_ADMIN",
            is_active=True,
            is_account_active=True,
        )

    def credentials(self, user):
        return {
            "username": user.username,
            "password": self.password,
        }

    def test_bde_login_accepts_bde(self):
        response = self.client.post(
            reverse("accounts:login"),
            self.credentials(self.bde),
        )

        self.assertRedirects(
            response,
            reverse("dashboard:home"),
            fetch_redirect_response=False,
        )

        self.assertEqual(
            int(
                self.client.session[
                    "_auth_user_id"
                ]
            ),
            self.bde.pk,
        )

        self.assertTrue(
            LoginSession.objects.filter(
                user=self.bde,
                is_active=True,
            ).exists()
        )

    def test_admin_rejected_at_bde_login(self):
        response = self.client.post(
            reverse("accounts:login"),
            self.credentials(self.admin),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "administrator account",
        )

        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_admin_login_accepts_admin(self):
        response = self.client.post(
            reverse("accounts:admin_login"),
            self.credentials(self.admin),
        )

        self.assertRedirects(
            response,
            reverse(
                "dashboard:admin_overview"
            ),
            fetch_redirect_response=False,
        )

    def test_bde_rejected_at_admin_login(self):
        response = self.client.post(
            reverse("accounts:admin_login"),
            self.credentials(self.bde),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "BDE account",
        )

        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_next_root_cannot_override_admin(self):
        response = self.client.post(
            (
                reverse(
                    "accounts:admin_login"
                )
                + "?next=/"
            ),
            self.credentials(self.admin),
        )

        self.assertRedirects(
            response,
            reverse(
                "dashboard:admin_overview"
            ),
            fetch_redirect_response=False,
        )

    def test_unauthenticated_admin_center_uses_admin_login(self):
        response = self.client.get(
            reverse(
                "dashboard:admin_overview"
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            response.url.startswith(
                reverse(
                    "accounts:admin_login"
                )
            )
        )

    def test_admin_cannot_open_bde_dashboard(self):
        self.client.force_login(
            self.admin
        )

        response = self.client.get(
            reverse("dashboard:home")
        )

        self.assertRedirects(
            response,
            reverse(
                "dashboard:admin_overview"
            ),
            fetch_redirect_response=False,
        )

    def test_logout_is_role_aware(self):
        self.client.force_login(
            self.admin
        )

        admin_response = self.client.post(
            reverse("accounts:logout")
        )

        self.assertRedirects(
            admin_response,
            reverse(
                "accounts:admin_login"
            ),
            fetch_redirect_response=False,
        )

        self.client.force_login(
            self.bde
        )

        bde_response = self.client.post(
            reverse("accounts:logout")
        )

        self.assertRedirects(
            bde_response,
            reverse("accounts:login"),
            fetch_redirect_response=False,
        )
