# BNW_STANDARD_IMPORT_FINALIZE_V1

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve, reverse

from toolkit import import_views


class StandardImportFinalizeWiringTests(
    SimpleTestCase
):

    def test_standard_import_has_its_own_view(self):

        url = reverse(
            "toolkit:import_finalize",
            args=[8],
        )

        match = resolve(url)

        self.assertIs(
            match.func,
            import_views.import_finalize,
        )

        self.assertEqual(
            url,
            "/admin-center/import/8/apply/",
        )

    def test_review_form_does_not_use_reconciliation(self):

        path = (
            Path(settings.BASE_DIR)
            / "toolkit/templates/toolkit/admin/"
            / "extraction_review.html"
        )

        text = path.read_text(
            encoding="utf-8"
        )

        marker = 'id="bnx-final-import-form"'
        marker_position = text.index(marker)

        form_start = text.rfind(
            "<form",
            0,
            marker_position,
        )

        form_end = text.find(
            "</form>",
            marker_position,
        )

        form = text[
            form_start:
            form_end
        ]

        self.assertIn(
            "'toolkit:import_finalize'",
            form,
        )

        self.assertNotIn(
            "'toolkit:reconciliation_finalize'",
            form,
        )

        self.assertIn(
            'value="final_import"',
            form,
        )
