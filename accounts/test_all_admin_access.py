from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AllAdminRolesFullAccessTests(TestCase):
    password = "Temporary-Test-Password-2026!"

    admin_roles = (
        "DATA_ADMIN",
        "SECURITY_ADMIN",
        "IT_ADMIN",
        "SUPER_ADMIN",
    )

    sidebar_labels = (
        "Overview",
        "BDE Analytics",
        "Employees",
        "Toolkit Management",
        "Flyer Manager",
        "Pitch Windows",
        "Import Data",
        "Source History",
        "Database Map",
        "Activity Logs",
    )

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.bde = User.objects.create_user(
            username="unified.access.bde",
            password=cls.password,
            employee_id="BNXT-UNIFIED-BDE-001",
            role="BDE",
            is_active=True,
            is_account_active=True,
        )

        cls.admins = {}

        for number, role in enumerate(
            cls.admin_roles,
            start=1,
        ):
            cls.admins[role] = (
                User.objects.create_user(
                    username=(
                        "unified."
                        + role.lower()
                    ),
                    password=cls.password,
                    employee_id=(
                        "BNXT-UNIFIED-ADMIN-"
                        + str(number).zfill(3)
                    ),
                    role=role,
                    is_active=True,
                    is_account_active=True,
                )
            )

    def module_urls(self):
        return (
            reverse(
                "dashboard:admin_overview"
            ),
            reverse(
                "dashboard:bde_analytics"
            ),
            reverse(
                "accounts:employee_list"
            ),
            reverse(
                "accounts:employee_create"
            ),
            reverse(
                "accounts:employee_edit",
                args=[self.bde.pk],
            ),
            reverse(
                "toolkit:admin_service_list"
            ),
            reverse(
                "toolkit:flyer_manager"
            ),
            reverse(
                "toolkit:pitch_windows"
            ),
            reverse(
                "toolkit:import_center"
            ),
            reverse(
                "toolkit:import_history"
            ),
            reverse(
                "toolkit:database_map"
            ),
            reverse(
                "accounts:activity_logs"
            ),
        )

    def test_every_admin_role_can_open_every_module(self):
        for role, admin in self.admins.items():
            self.client.force_login(admin)

            for url in self.module_urls():
                with self.subTest(
                    role=role,
                    url=url,
                ):
                    response = self.client.get(url)

                    self.assertEqual(
                        response.status_code,
                        200,
                        (
                            f"{role} received "
                            f"{response.status_code} "
                            f"for {url}"
                        ),
                    )

            self.client.logout()

    def test_every_admin_sees_every_sidebar_module(self):
        overview_url = reverse(
            "dashboard:admin_overview"
        )

        for role, admin in self.admins.items():
            self.client.force_login(admin)

            response = self.client.get(
                overview_url
            )

            self.assertEqual(
                response.status_code,
                200,
            )

            for label in self.sidebar_labels:
                with self.subTest(
                    role=role,
                    label=label,
                ):
                    self.assertContains(
                        response,
                        label,
                    )

            self.client.logout()

    def test_every_admin_can_assign_every_custom_role(self):
        create_url = reverse(
            "accounts:employee_create"
        )

        expected_values = (
            "BDE",
            "DATA_ADMIN",
            "SECURITY_ADMIN",
            "IT_ADMIN",
            "SUPER_ADMIN",
        )

        for role, admin in self.admins.items():
            self.client.force_login(admin)

            response = self.client.get(
                create_url
            )

            self.assertEqual(
                response.status_code,
                200,
            )

            for expected_value in expected_values:
                with self.subTest(
                    role=role,
                    expected_value=expected_value,
                ):
                    self.assertContains(
                        response,
                        (
                            f'value="'
                            f'{expected_value}'
                            f'"'
                        ),
                    )

            self.client.logout()

    def test_bde_is_blocked_from_every_admin_module(self):
        self.client.force_login(self.bde)

        for url in self.module_urls():
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(
                    response.status_code,
                    403,
                    (
                        "BDE should receive 403 "
                        f"for {url}, received "
                        f"{response.status_code}"
                    ),
                )
