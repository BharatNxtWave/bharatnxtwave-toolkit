from inspect import getsource
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from toolkit import import_views


class ChangedInformationReviewUiRegressionTests(
    SimpleTestCase
):

    def setUp(self):
        self.template = (
            Path(settings.BASE_DIR)
            / "toolkit"
            / "templates"
            / "toolkit"
            / "admin"
            / "extraction_review.html"
        ).read_text(encoding="utf-8")

    def test_review_view_uses_final_delta_classifier(self):
        source = getsource(
            import_views.import_extraction_review
        )

        self.assertIn(
            "classify_candidate",
            source,
        )
        self.assertIn(
            "row.is_changed_information",
            source,
        )
        self.assertIn(
            "row.needs_attention",
            source,
        )
        self.assertIn(
            '"safe_update"',
            source,
        )

    def test_replacement_is_presented_as_blocked(self):
        self.assertIn(
            "Replacement information is protected.",
            self.template,
        )
        self.assertIn(
            "Replacement Blocked",
            self.template,
        )
        self.assertIn(
            "{% if row.can_approve_import %}",
            self.template,
        )
        self.assertIn(
            "stats.needs_attention",
            self.template,
        )
        self.assertIn(
            "stats.safe_update",
            self.template,
        )

    def test_direct_replacement_approval_is_guarded(self):
        source = getsource(
            import_views.import_extraction_row_decision
        )

        self.assertIn(
            'approval_delta_status',
            source,
        )
        self.assertIn(
            '== "CHANGED_INFORMATION"',
            source,
        )
        self.assertIn(
            "Approval blocked:",
            source,
        )
