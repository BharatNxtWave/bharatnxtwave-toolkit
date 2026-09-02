from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase
from django.utils.html import strip_tags


class ReviewInstructionPanelRegressionTests(
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

        source = (
            root
            / "toolkit/templates/toolkit/admin/"
              "extraction_review.html"
        ).read_text(
            encoding="utf-8"
        )

        start_marker = (
            "<!-- WHAT YOU ACTUALLY NEED TO DO -->"
        )
        end_marker = "<!-- KPIS -->"

        start = source.index(start_marker)
        end = source.index(end_marker, start)

        cls.panel = Template(
            source[start:end]
        )

    @staticmethod
    def visible_text(value):
        return " ".join(
            strip_tags(value).split()
        )

    def render_panel(
        self,
        *,
        needs_attention=0,
        create=0,
        safe_update=0,
        skipped=0,
    ):
        rendered = self.panel.render(
            Context(
                {
                    "stats": {
                        "needs_attention":
                            needs_attention,
                        "create":
                            create,
                        "safe_update":
                            safe_update,
                        "skipped":
                            skipped,
                    }
                }
            )
        )

        return self.visible_text(rendered)

    def test_skipped_only_state_is_clear(self):
        text = self.render_panel(
            skipped=1,
        )

        self.assertIn(
            "Review is complete",
            text,
        )

        self.assertIn(
            "1 skipped item will remain excluded",
            text,
        )

        self.assertIn(
            "without changing Toolkit data",
            text,
        )

        self.assertNotIn(
            "uncertain match",
            text,
        )

    def test_zero_state_hides_zero_count_tasks(self):
        text = self.render_panel()

        self.assertIn(
            "No Service changes need review",
            text,
        )

        self.assertIn(
            "No pending Service decision remains",
            text,
        )

        self.assertNotIn(
            "Review 0",
            text,
        )

        self.assertNotIn(
            "0 new Service",
            text,
        )

        self.assertNotIn(
            "0 existing Service",
            text,
        )

    def test_active_tasks_show_correct_wording(self):
        text = self.render_panel(
            needs_attention=2,
            create=1,
            safe_update=3,
        )

        self.assertIn(
            "2 items requiring attention",
            text,
        )

        self.assertIn(
            "1 new Service before creation",
            text,
        )

        self.assertIn(
            "3 existing Service rows",
            text,
        )

        self.assertNotIn(
            "uncertain match",
            text,
        )
