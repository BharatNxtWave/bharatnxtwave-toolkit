"""Tests for the background import queue and worker.

Applying an import used to happen inside the HTTP request. It now goes
through a queue, which moves a safety-critical flow onto a new code path, so
the properties that matter are asserted directly:

  * the request queues and returns instead of importing;
  * the worker actually applies what was queued;
  * two workers can never both claim the same batch;
  * a worker killed mid-import leaves a batch that can be retried, not one
    stuck in IMPORTING forever.
"""

from hashlib import sha256
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from toolkit.models import (
    Category,
    ImportBatch,
    ImportRow,
    Service,
    ServiceDomain,
)


User = get_user_model()

FINAL_IMPORT = "toolkit.intelligence.final_import"

# The worker binds apply_batch/rollback_batch at import time, so patching
# them on the final_import module would not affect the worker's own names.
WORKER = "toolkit.management.commands.run_import_worker"


class ImportQueueTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.domain = ServiceDomain.objects.create(
            name="Worker Domain",
            slug="worker-domain",
            description="Automated test domain.",
        )

        cls.category = Category.objects.create(
            domain=cls.domain,
            name="Worker Category",
            slug="worker-category",
            description="Automated test category.",
        )

        cls.service_kind = Service.SERVICE_KIND_CHOICES[0][0]

        cls.admin = User.objects.create_user(
            username="worker_admin",
            password="worker-test-password-1234",
            role="DATA_ADMIN",
        )

    def make_batch(self, status="PREVIEWED"):
        number = ImportBatch.objects.count() + 1

        return ImportBatch.objects.create(
            source_type="XLSX",
            source_name=f"worker-{number}.xlsx",
            source_identifier=f"worker-source-{number}",
            file_sha256="",
            sheet_count=1,
            row_count=1,
            status=status,
            metadata={},
        )

    def make_row(self, batch, action="CREATE", decision="APPROVED",
                 title="Worker Test Scheme", row_number=2):
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
                "reason": "Automated worker test.",
                "reviewed_at": None,
                "reviewed_by_id": None,
                "category_id": self.category.pk,
                "service_kind": self.service_kind,
            },
        }

        fingerprint = sha256(
            f"{batch.pk}:{row_number}:{title}".encode("utf-8")
        ).hexdigest()

        row = ImportRow.objects.create(
            import_batch=batch,
            sheet_name="Schemes",
            source_row_number=row_number,
            source_key=f"worker-{batch.pk}-{row_number}",
            row_hash=fingerprint,
            raw_data=raw_data,
            validation_status="VALID",
            candidate_action=action,
        )

        batch.row_count = batch.rows.count()
        batch.save(update_fields=["row_count"])

        return row


class FinalizeQueuesTests(ImportQueueTestCase):
    """The request must queue, not import."""

    def setUp(self):
        self.client.force_login(self.admin)
        self.batch = self.make_batch()
        self.make_row(self.batch)

    def _finalize(self):
        return self.client.post(
            reverse(
                "toolkit:import_finalize",
                kwargs={"batch_id": self.batch.pk},
            ),
            {"action": "final_import"},
        )

    def test_finalize_leaves_the_batch_queued(self):
        self._finalize()
        self.batch.refresh_from_db()

        self.assertEqual(self.batch.status, "QUEUED")

    def test_finalize_does_not_apply_inline(self):
        """The regression that motivated the queue.

        Asserted on the observable outcome rather than on a patch: the
        request must not have written the catalogue, and must not have
        taken a database snapshot. If this fails, applying is back inside
        the request - blocking a gunicorn worker and exposed to the 120s
        request timeout.
        """

        services_before = Service.objects.count()

        with patch(f"{FINAL_IMPORT}.backup_database") as backup:
            self._finalize()

        self.assertFalse(
            backup.called,
            "The request took a database snapshot - the import ran inline.",
        )

        self.assertEqual(
            Service.objects.count(),
            services_before,
            "The request created services - the import ran inline.",
        )

    def test_finalize_records_who_queued_it(self):
        self._finalize()
        self.batch.refresh_from_db()

        self.assertEqual(
            self.batch.metadata.get("queued_by_id"),
            self.admin.pk,
        )

    def test_an_already_queued_batch_is_not_queued_twice(self):
        self._finalize()
        self.batch.refresh_from_db()
        first_queued_at = self.batch.metadata.get("queued_at")

        self._finalize()
        self.batch.refresh_from_db()

        self.assertEqual(self.batch.status, "QUEUED")
        self.assertEqual(
            self.batch.metadata.get("queued_at"),
            first_queued_at,
        )


class WorkerTests(ImportQueueTestCase):

    def _run_worker(self, **kwargs):
        out, err = StringIO(), StringIO()
        call_command(
            "run_import_worker",
            once=True,
            stdout=out,
            stderr=err,
            **kwargs,
        )
        return out.getvalue() + err.getvalue()

    def test_worker_applies_a_queued_batch(self):
        batch = self.make_batch(status="QUEUED")
        self.make_row(batch)

        with patch(f"{FINAL_IMPORT}.backup_database", return_value="/tmp/x"):
            self._run_worker()

        batch.refresh_from_db()

        self.assertEqual(batch.status, "IMPORTED")

    def test_worker_ignores_batches_that_are_not_queued(self):
        batch = self.make_batch(status="PREVIEWED")
        self.make_row(batch)

        with patch(f"{FINAL_IMPORT}.backup_database", return_value="/tmp/x"):
            self._run_worker()

        batch.refresh_from_db()

        self.assertEqual(batch.status, "PREVIEWED")

    def test_a_batch_is_claimed_only_once(self):
        """Two workers racing must not both import the same batch."""

        batch = self.make_batch(status="QUEUED")
        self.make_row(batch)

        from toolkit.management.commands.run_import_worker import Command

        first = Command()
        second = Command()

        claimed_first = first._claim()
        claimed_second = second._claim()

        self.assertIsNotNone(claimed_first)
        self.assertIsNone(
            claimed_second,
            "Two workers both claimed the same batch.",
        )

    def test_claim_moves_the_batch_out_of_the_queue(self):
        batch = self.make_batch(status="QUEUED")
        self.make_row(batch)

        from toolkit.management.commands.run_import_worker import Command

        Command()._claim()
        batch.refresh_from_db()

        self.assertEqual(batch.status, "IMPORTING")
        self.assertIn("import_claimed_at", batch.metadata)

    def test_failure_is_recorded_on_the_batch(self):
        batch = self.make_batch(status="QUEUED")
        self.make_row(batch)

        with patch(
            f"{FINAL_IMPORT}.backup_database",
            side_effect=RuntimeError("disk full"),
        ):
            output = self._run_worker()

        batch.refresh_from_db()

        self.assertEqual(batch.status, "FAILED")
        self.assertIn("disk full", batch.metadata.get("import_failure", ""))
        self.assertIn("failed", output.lower())

    def test_stuck_batch_is_recovered(self):
        """A worker killed mid-import must not strand the batch."""

        batch = self.make_batch(status="IMPORTING")
        self.make_row(batch)

        stale = timezone.now() - timezone.timedelta(hours=4)
        batch.metadata = {"import_claimed_at": stale.isoformat()}
        batch.save(update_fields=["metadata"])

        self._run_worker()

        batch.refresh_from_db()

        self.assertEqual(batch.status, "FAILED")
        self.assertIn(
            "Worker stopped",
            batch.metadata.get("import_failure", ""),
        )

    def test_a_recently_claimed_batch_is_left_alone(self):
        """An import genuinely in progress must not be marked failed."""

        batch = self.make_batch(status="IMPORTING")
        self.make_row(batch)

        batch.metadata = {
            "import_claimed_at": timezone.now().isoformat()
        }
        batch.save(update_fields=["metadata"])

        self._run_worker()

        batch.refresh_from_db()

        self.assertEqual(batch.status, "IMPORTING")

    def test_empty_queue_is_a_no_op(self):
        output = self._run_worker()

        self.assertIn("Import worker", output)


class RollbackQueueTests(ImportQueueTestCase):
    """Rollback goes through the same queue, and fails back to IMPORTED."""

    def _run_worker(self, **kwargs):
        out, err = StringIO(), StringIO()
        call_command(
            "run_import_worker", once=True,
            stdout=out, stderr=err, **kwargs,
        )
        return out.getvalue() + err.getvalue()

    def _queued_rollback(self):
        batch = self.make_batch(status="QUEUED")
        self.make_row(batch)
        batch.metadata = {
            "queued_operation": "rollback",
            "queued_by_id": self.admin.pk,
        }
        batch.save(update_fields=["metadata"])
        return batch

    def test_worker_calls_rollback_not_apply(self):
        batch = self._queued_rollback()

        with patch(f"{WORKER}.rollback_batch",
                   return_value={"reversed_changes": 3}) as rollback:
            with patch(f"{WORKER}.apply_batch") as apply_batch:
                self._run_worker()

        self.assertTrue(rollback.called)
        self.assertFalse(
            apply_batch.called,
            "A queued rollback was applied as an import.",
        )
        self.assertEqual(
            rollback.call_args.kwargs["expected_statuses"],
            {"IMPORTING"},
        )
        self.assertEqual(rollback.call_args.args[0], batch.pk)

    def test_failed_rollback_returns_to_imported_not_failed(self):
        """The import it was reversing is still applied.

        Leaving the batch FAILED would say the opposite and invite someone
        to re-run the import.
        """

        batch = self._queued_rollback()

        with patch(f"{WORKER}.rollback_batch",
                   side_effect=RuntimeError("connection lost")):
            self._run_worker()

        batch.refresh_from_db()

        self.assertEqual(batch.status, "IMPORTED")
        self.assertIn(
            "connection lost",
            batch.metadata.get("import_failure", ""),
        )

    def test_stranded_rollback_returns_to_imported(self):
        batch = self.make_batch(status="IMPORTING")
        self.make_row(batch)

        stale = timezone.now() - timezone.timedelta(hours=4)
        batch.metadata = {
            "queued_operation": "rollback",
            "import_claimed_at": stale.isoformat(),
        }
        batch.save(update_fields=["metadata"])

        self._run_worker()
        batch.refresh_from_db()

        self.assertEqual(batch.status, "IMPORTED")
        self.assertIn("rollback", batch.metadata.get("import_failure", ""))
