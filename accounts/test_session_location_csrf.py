from pathlib import Path

from django.test import SimpleTestCase


class SessionLocationCsrfRegressionTests(
    SimpleTestCase
):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        root = (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )

        cls.javascript = (
            root
            / "static/js/session_location.js"
        ).read_text(
            encoding="utf-8"
        )

    def test_current_page_token_is_preferred(self):
        self.assertIn(
            "function getCsrfToken()",
            self.javascript,
        )

        self.assertIn(
            'input[name="csrfmiddlewaretoken"]',
            self.javascript,
        )

        form_position = self.javascript.index(
            'input[name="csrfmiddlewaretoken"]'
        )

        cookie_position = self.javascript.index(
            'getCookie("csrftoken")',
            form_position,
        )

        self.assertLess(
            form_position,
            cookie_position,
        )

    def test_missing_token_does_not_send_request(self):
        self.assertIn(
            "if (!csrfToken)",
            self.javascript,
        )

        self.assertIn(
            '"X-CSRFToken": csrfToken',
            self.javascript,
        )

    def test_direct_hardcoded_cookie_header_is_removed(self):
        self.assertNotIn(
            '"X-CSRFToken": getCookie("csrftoken")',
            self.javascript,
        )
