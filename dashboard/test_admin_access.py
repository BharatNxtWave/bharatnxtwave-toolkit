from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AdminCenterAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.bde = User.objects.create_user(
            username="access.test.bde",
            password="Temporary-Test-Password-2026!",
            employee_id="BNXT-ACCESS-BDE-001",
            role="BDE",
            is_active=True,
            is_account_active=True,
        )

        cls.super_admin = User.objects.create_superuser(
            username="access.test.admin",
            password="Temporary-Test-Password-2026!",
            employee_id="BNXT-ACCESS-ADMIN-001",
            role="SUPER_ADMIN",
            is_account_active=True,
        )

    def test_bde_receives_403_instead_of_dashboard_redirect(self):
        self.client.force_login(self.bde)

        response = self.client.get(
            reverse("dashboard:admin_overview")
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "Admin Center access denied",
            status_code=403,
        )

    def test_super_admin_can_open_admin_center(self):
        self.client.force_login(self.super_admin)

        response = self.client.get(
            reverse("dashboard:admin_overview")
        )

        self.assertEqual(response.status_code, 200)
