"""Tests for the environment-driven first administrator.

This creates a full-access account from a password in the environment, so
the guards around it matter more than the happy path.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings


User = get_user_model()

STRONG = "vT7-quiet-harbour-9412"


def env(**kwargs):
    base = {
        "BHARATNXT_BOOTSTRAP_ADMIN_USERNAME": "bootadmin",
        "BHARATNXT_BOOTSTRAP_ADMIN_PASSWORD": STRONG,
        "BHARATNXT_BOOTSTRAP_ADMIN_EMAIL": "boot@example.com",
    }
    base.update(kwargs)
    return base


class BootstrapAdminTests(TestCase):

    def run_command(self, **environ):
        import os
        from unittest.mock import patch

        out, err = StringIO(), StringIO()

        with patch.dict(os.environ, environ, clear=False):
            call_command("bootstrap_admin", stdout=out, stderr=err)

        return out.getvalue() + err.getvalue()

    def test_creates_a_super_admin(self):
        self.run_command(**env())

        user = User.objects.get(username="bootadmin")

        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertEqual(user.role, "SUPER_ADMIN")
        self.assertTrue(user.check_password(STRONG))

    def test_does_nothing_when_a_superuser_exists(self):
        User.objects.create_superuser(
            username="existing", password=STRONG, role="SUPER_ADMIN"
        )

        self.run_command(**env())

        self.assertFalse(
            User.objects.filter(username="bootadmin").exists()
        )

    def test_is_idempotent_across_restarts(self):
        self.run_command(**env())
        first = User.objects.get(username="bootadmin").password

        self.run_command(**env(
            BHARATNXT_BOOTSTRAP_ADMIN_PASSWORD="a-different-password-8891"
        ))

        self.assertEqual(
            User.objects.get(username="bootadmin").password,
            first,
            "A restart reset the administrator's password.",
        )

    def test_short_password_is_refused(self):
        output = self.run_command(**env(
            BHARATNXT_BOOTSTRAP_ADMIN_PASSWORD="short1"
        ))

        self.assertIn("Refusing", output)
        self.assertFalse(User.objects.filter(username="bootadmin").exists())

    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {"NAME": "django.contrib.auth.password_validation."
                 "CommonPasswordValidator"},
    ])
    def test_common_password_is_refused(self):
        output = self.run_command(**env(
            BHARATNXT_BOOTSTRAP_ADMIN_PASSWORD="password123456"
        ))

        self.assertIn("Refusing", output)
        self.assertFalse(User.objects.filter(username="bootadmin").exists())

    def test_missing_variables_are_reported(self):
        output = self.run_command(
            BHARATNXT_BOOTSTRAP_ADMIN_USERNAME="",
            BHARATNXT_BOOTSTRAP_ADMIN_PASSWORD="",
        )

        self.assertIn("must both be set", output)

    def test_existing_non_superuser_is_not_promoted(self):
        """Silently turning a BDE into a full admin would be a surprise."""

        User.objects.create_user(
            username="bootadmin", password=STRONG, role="BDE"
        )

        output = self.run_command(**env())

        self.assertIn("Refusing", output)

        user = User.objects.get(username="bootadmin")
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.role, "BDE")
