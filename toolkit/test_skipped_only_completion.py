from pathlib import Path

from django.test import SimpleTestCase


class SkippedOnlyCompletionRegressionTests(
    SimpleTestCase
):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.root = (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )

        cls.template = (
            cls.root
            / "toolkit/templates/toolkit/admin/"
              "extraction_review.html"
        ).read_text(
            encoding="utf-8"
        )

        cls.views = (
            cls.root
            / "toolkit/import_views.py"
        ).read_text(
            encoding="utf-8"
        )

    def test_template_exposes_skipped_count(self):
        self.assertIn(
            'data-skipped-count="{{ stats.skipped }}"',
            self.template,
        )

        self.assertIn(
            "card.dataset.skippedCount",
            self.template,
        )

    def test_skipped_only_review_can_be_finished(self):
        self.assertIn(
            "}else if(skippedCount > 0){",
            self.template,
        )

        self.assertIn(
            '"Finish review →"',
            self.template,
        )

        self.assertIn(
            "All reviewed items were skipped.",
            self.template,
        )

    def test_pending_manual_review_still_blocks_import(self):
        review_branch = self.template.index(
            "if(reviewCount > 0){"
        )

        skipped_branch = self.template.index(
            "}else if(skippedCount > 0){"
        )

        self.assertLess(
            review_branch,
            skipped_branch,
        )

    def test_skipped_completion_uses_standard_finalize(self):
        self.assertIn(
            "action="
            '"{% url '
            "'toolkit:import_finalize' "
            'batch.pk %}"',
            self.template,
        )

        self.assertIn(
            'value="final_import"',
            self.template,
        )

    def test_completion_message_confirms_no_data_change(self):
        self.assertIn(
            "Review completed.",
            self.views,
        )

        self.assertIn(
            "No Toolkit data was changed.",
            self.views,
        )

        self.assertIn(
            'candidate_action="SKIP"',
            self.views,
        )
