from pathlib import Path

from django.test import TestCase

from toolkit.import_views import (
    _with_toolkit_change_status,
)
from toolkit.models import (
    ImportBatch,
    ImportChange,
)


class ImportStatusWordingRegressionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.updated_batch = ImportBatch.objects.create(
            source_type="XLSX",
            source_name="updated-toolkit.xlsx",
            file_sha256="1" * 64,
            row_count=1,
            status="IMPORTED",
        )

        ImportChange.objects.create(
            import_batch=cls.updated_batch,
            action="SERVICE_CREATE",
        )

        cls.zero_change_batch = (
            ImportBatch.objects.create(
                source_type="XLSX",
                source_name="completed-no-changes.xlsx",
                file_sha256="2" * 64,
                row_count=1,
                status="IMPORTED",
            )
        )

    def test_annotation_distinguishes_real_changes(self):
        batches = {
            batch.pk: batch
            for batch in _with_toolkit_change_status(
                ImportBatch.objects.filter(
                    pk__in=[
                        self.updated_batch.pk,
                        self.zero_change_batch.pk,
                    ]
                )
            )
        }

        self.assertTrue(
            batches[
                self.updated_batch.pk
            ].has_toolkit_changes
        )

        self.assertFalse(
            batches[
                self.zero_change_batch.pk
            ].has_toolkit_changes
        )

    def test_database_status_remains_imported(self):
        self.updated_batch.refresh_from_db()
        self.zero_change_batch.refresh_from_db()

        self.assertEqual(
            self.updated_batch.status,
            "IMPORTED",
        )

        self.assertEqual(
            self.zero_change_batch.status,
            "IMPORTED",
        )

    def test_both_templates_use_clear_wording(self):
        template_root = (
            Path(__file__).resolve().parent
            / "templates"
            / "toolkit"
            / "admin"
        )

        combined = (
            (
                template_root
                / "import_history.html"
            ).read_text(encoding="utf-8")
            +
            (
                template_root
                / "import_history_detail.html"
            ).read_text(encoding="utf-8")
        )

        self.assertIn(
            "Imported — Toolkit updated",
            combined,
        )

        self.assertIn(
            "Completed — no Toolkit changes",
            combined,
        )

        self.assertIn(
            "batch.has_toolkit_changes",
            combined,
        )
