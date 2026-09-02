# BNW_SIDEBAR_PASSWORD_UI_V1
from pathlib import Path

from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase


class SidebarAndPasswordUiTests(
    SimpleTestCase
):
    def test_login_pages_load_password_toggle(self):
        for template_name in (
            "accounts/login.html",
            "accounts/admin_login.html",
        ):
            template = get_template(
                template_name
            )

            source = Path(
                template.origin.name
            ).read_text(
                encoding="utf-8"
            )

            self.assertIn(
                "password_visibility.js",
                source,
            )

    def test_admin_navigation_has_distinct_states(self):
        source = (
            Path(settings.BASE_DIR)
            / "templates"
            / "admin_base.html"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "'/admin-center/import/history/' "
            "not in request.path",
            source,
        )

        self.assertIn(
            "url_name == 'import_history'",
            source,
        )

        self.assertIn(
            "url_name == 'database_map'",
            source,
        )

    def test_password_assets_exist(self):
        base = Path(settings.BASE_DIR)

        script = (
            base
            / "static"
            / "js"
            / "password_visibility.js"
        ).read_text(
            encoding="utf-8"
        )

        styles = (
            base
            / "static"
            / "css"
            / "app.css"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "BNW_PASSWORD_VISIBILITY_V1",
            script,
        )

        self.assertIn(
            "BNW_PASSWORD_VISIBILITY_V1",
            styles,
        )
