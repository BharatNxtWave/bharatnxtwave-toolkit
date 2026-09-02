# BNW_IMPORT_SAFETY_TESTS_V1

from hashlib import sha256
from unittest.mock import patch

from django.test import TestCase

from toolkit.intelligence.final_import import (
    DuplicateSourceError,
    FinalImportError,
    _apply_difference,
    _create_service,
    _decision,
    apply_batch,
    duplicate_imported_batch,
    preview_batch,
)
from toolkit.models import (
    Category,
    ImportBatch,
    ImportChange,
    ImportRow,
    Service,
    ServiceDomain,
)


FINAL_IMPORT_MODULE = "toolkit.intelligence.final_import"


class ImportSafetyRegressionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.domain = ServiceDomain.objects.create(
            name="Import Safety Domain",
            slug="import-safety-domain",
            description="Automated test classification.",
        )

        cls.category = Category.objects.create(
            domain=cls.domain,
            name="Import Safety Category",
            slug="import-safety-category",
            description="Automated test classification.",
        )

        cls.service_kind = Service.SERVICE_KIND_CHOICES[0][0]

    def make_batch(self, status="PREVIEWED", checksum=""):
        number = ImportBatch.objects.count() + 1

        return ImportBatch.objects.create(
            source_type="XLSX",
            source_name=f"import-safety-{number}.xlsx",
            source_identifier=f"test-source-{number}",
            file_sha256=checksum,
            sheet_count=1,
            row_count=0,
            status=status,
            metadata={},
        )

    def make_row(
        self,
        batch,
        *,
        decision="PENDING",
        action="CREATE",
        title="Automated Import Safety Scheme",
        category_id=None,
        row_number=2,
    ):
        if category_id is None:
            category_id = self.category.pk

        source_data = {
            "row_number": row_number,
            "values": {"Scheme Name": title},
            "links": [],
        }

        raw_data = {
            "engine_version": "automated-test-v1",
            "sheet_kind": "SCHEME",
            "business_knowledge_visibility": "ADMIN_ONLY",

            "source": source_data,

            "candidate": {
                "title": title,
                "fields": {},
                "links": [],
                "match": {},
                "proposal": {},
                "source_row": source_data,
                "extraction_mode": "AUTOMATED_TEST",
            },

            "review": {
                "automatic": False,
                "decision": decision,
                "reason": "Automated importer safety test.",
                "reviewed_at": None,
                "reviewed_by_id": None,
                "category_id": category_id,
                "service_kind": self.service_kind,
            },
        }

        fingerprint = sha256(
            (
                f"{batch.pk}:{row_number}:"
                f"{title}:{decision}:{action}"
            ).encode("utf-8")
        ).hexdigest()

        row = ImportRow.objects.create(
            import_batch=batch,
            sheet_name="Schemes",
            source_row_number=row_number,
            source_key=f"test-{batch.pk}-{row_number}",
            row_hash=fingerprint,
            raw_data=raw_data,
            validation_status="VALID",
            candidate_action=action,
        )

        batch.row_count = ImportRow.objects.filter(
            import_batch=batch
        ).count()

        batch.save(update_fields=["row_count"])

        return row

    def apply_using_test_database(self, batch):
        # Production uses a physical SQLite backup.
        # Django tests use a temporary in-memory database.
        with patch(
            f"{FINAL_IMPORT_MODULE}.backup_database",
            return_value=None,
        ):
            return apply_batch(batch.pk)

    def test_approved_new_scheme_creates_service_and_ledger(self):
        batch = self.make_batch()

        row = self.make_row(
            batch,
            decision="APPROVED",
        )

        service_count = Service.objects.count()
        change_count = ImportChange.objects.count()

        service = _create_service(
            batch,
            row,
            row.raw_data["candidate"],
        )

        self.assertEqual(
            Service.objects.count(),
            service_count + 1,
        )

        self.assertEqual(
            ImportChange.objects.count(),
            change_count + 1,
        )

        self.assertTrue(service.service_id)
        self.assertTrue(service.slug)
        self.assertEqual(service.status, "PUBLISHED")
        self.assertEqual(service.category_id, self.category.pk)
        self.assertEqual(service.domain_id, self.domain.pk)
        self.assertEqual(service.service_kind, self.service_kind)

        self.assertTrue(
            ImportChange.objects.filter(
                import_batch=batch,
                import_row=row,
                service=service,
                action="SERVICE_CREATE",
            ).exists()
        )

    def test_new_scheme_without_category_is_rejected(self):
        batch = self.make_batch()

        row = self.make_row(
            batch,
            decision="APPROVED",
        )

        raw_data = dict(row.raw_data)
        review = dict(raw_data["review"])
        review["category_id"] = None
        raw_data["review"] = review

        row.raw_data = raw_data
        row.save(update_fields=["raw_data"])

        service_count = Service.objects.count()
        change_count = ImportChange.objects.count()

        with self.assertRaises(FinalImportError):
            _create_service(
                batch,
                row,
                row.raw_data["candidate"],
            )

        self.assertEqual(Service.objects.count(), service_count)
        self.assertEqual(ImportChange.objects.count(), change_count)

    def test_exact_duplicate_import_is_blocked(self):
        checksum = "a" * 64

        imported_batch = self.make_batch(
            status="IMPORTED",
            checksum=checksum,
        )

        current_batch = self.make_batch(
            status="PREVIEWED",
            checksum=checksum,
        )

        duplicate = duplicate_imported_batch(current_batch)

        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate.pk, imported_batch.pk)

        service_count = Service.objects.count()

        with self.assertRaises(DuplicateSourceError):
            apply_batch(current_batch.pk)

        current_batch.refresh_from_db()

        self.assertEqual(current_batch.status, "PREVIEWED")
        self.assertEqual(Service.objects.count(), service_count)

    def test_pending_row_blocks_final_import(self):
        batch = self.make_batch()

        self.make_row(
            batch,
            decision="PENDING",
            action="CREATE",
        )

        preview = preview_batch(batch.pk)

        self.assertEqual(preview["pending_changes"], 1)

        service_count = Service.objects.count()

        with self.assertRaises(FinalImportError):
            apply_batch(batch.pk)

        batch.refresh_from_db()

        self.assertEqual(batch.status, "PREVIEWED")
        self.assertEqual(Service.objects.count(), service_count)

    def test_skipped_row_creates_no_service(self):
        batch = self.make_batch()

        row = self.make_row(
            batch,
            decision="APPROVED",
            action="SKIP",
        )

        self.assertEqual(_decision(row), "SKIPPED")

        service_count = Service.objects.count()
        change_count = ImportChange.objects.count()

        result = self.apply_using_test_database(batch)

        batch.refresh_from_db()
        row.refresh_from_db()

        self.assertEqual(batch.status, "IMPORTED")
        self.assertEqual(result["created_services"], 0)
        self.assertIsNotNone(row.processed_at)
        self.assertIsNone(row.imported_service_id)

        self.assertEqual(Service.objects.count(), service_count)
        self.assertEqual(ImportChange.objects.count(), change_count)

    def test_replacement_information_is_not_overwritten(self):
        batch = self.make_batch()

        row = self.make_row(
            batch,
            decision="APPROVED",
        )

        service = _create_service(
            batch,
            row,
            row.raw_data["candidate"],
        )

        service.overview = "Original approved overview."
        service.save(update_fields=["overview"])

        change_count = ImportChange.objects.count()

        replacement = {
            "field": "overview",
            "incoming": "Replacement overview.",
            "change_type": "REPLACEMENT",
        }

        with self.assertRaises(FinalImportError):
            _apply_difference(
                batch,
                row,
                service,
                replacement,
            )

        service.refresh_from_db()

        self.assertEqual(
            service.overview,
            "Original approved overview.",
        )

        self.assertEqual(
            ImportChange.objects.count(),
            change_count,
        )

    def test_failed_creation_rolls_back_service_and_ledger(self):
        batch = self.make_batch()

        row = self.make_row(
            batch,
            decision="APPROVED",
            action="CREATE",
        )

        preview = preview_batch(batch.pk)

        self.assertEqual(preview["pending_changes"], 0)

        service_count = Service.objects.count()
        change_count = ImportChange.objects.count()

        with patch(
            f"{FINAL_IMPORT_MODULE}.backup_database",
            return_value=None,
        ), patch(
            f"{FINAL_IMPORT_MODULE}._record_change",
            side_effect=RuntimeError(
                "Forced importer transaction failure."
            ),
        ):
            with self.assertRaises(Exception) as captured:
                apply_batch(batch.pk)

        self.assertIn(
            "Forced importer transaction failure",
            str(captured.exception),
        )

        batch.refresh_from_db()
        row.refresh_from_db()

        self.assertEqual(batch.status, "FAILED")
        self.assertIsNone(row.processed_at)
        self.assertIsNone(row.imported_service_id)

        self.assertEqual(Service.objects.count(), service_count)
        self.assertEqual(ImportChange.objects.count(), change_count)
