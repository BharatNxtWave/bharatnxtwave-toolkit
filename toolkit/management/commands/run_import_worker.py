"""Apply queued import batches outside the request cycle.

Why
---
Applying an import takes a full `pg_dump` of the database and then rewrites
the catalogue. That used to happen inside the HTTP request that clicked
"apply", which meant:

  * one gunicorn worker was blocked for the whole import - a third of a
    three-worker instance, for minutes;
  * gunicorn's 120 second timeout would eventually kill the request outright
    as the database grew, failing the import with no useful message.

Now the view queues the batch and returns immediately, and this worker
applies it.

Running it
----------
    manage.py run_import_worker              # long-running (a service)
    manage.py run_import_worker --once       # single pass (cron)

On Render this is a Background Worker service sharing the image and database
(see render.yaml). Self-hosted, it is a second systemd unit.

Safe to run more than one copy: a batch is claimed with a single conditional
UPDATE, so exactly one worker wins it. Running none is also safe - imports
simply sit in the queue until a worker starts.
"""

import signal
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from toolkit.intelligence.final_import import (
    FinalImportError,
    apply_batch,
    rollback_batch,
)
from toolkit.models import ImportBatch


POLL_SECONDS = 5

# A batch claimed longer ago than this had its worker killed mid-import
# (deploy, OOM, crash). apply_batch runs inside a transaction, so the
# database is not half-written - but the row is stuck in IMPORTING and would
# never be retried.
STUCK_MINUTES = 60

CLAIMED_AT_KEY = "import_claimed_at"


class Command(BaseCommand):
    help = "Apply queued import batches in the background."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process whatever is queued, then exit.",
        )
        parser.add_argument(
            "--poll",
            type=int,
            default=POLL_SECONDS,
            help=f"Seconds between polls (default {POLL_SECONDS}).",
        )
        parser.add_argument(
            "--stuck-minutes",
            type=int,
            default=STUCK_MINUTES,
            help=(
                "Mark a batch FAILED if it has been IMPORTING longer than "
                f"this (default {STUCK_MINUTES})."
            ),
        )

    def handle(self, *args, **options):
        self.stopping = False

        # Render sends SIGTERM on deploy. Finish the batch in flight rather
        # than dying halfway through someone's import.
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._request_stop)
            except (ValueError, OSError):
                # Not on the main thread, or unsupported on this platform.
                pass

        once = options["once"]
        poll = max(1, options["poll"])
        stuck_minutes = max(1, options["stuck_minutes"])

        self.stdout.write("Import worker started.")

        self._recover_stuck(stuck_minutes)

        while not self.stopping:
            applied = self._process_one()

            if once and not applied:
                break

            if not applied and not self.stopping:
                time.sleep(poll)

        self.stdout.write("Import worker stopped.")

    # -- signals -------------------------------------------------------------

    def _request_stop(self, signum, frame):
        self.stdout.write(
            f"Signal {signum} received; stopping after the current batch."
        )
        self.stopping = True

    # -- recovery ------------------------------------------------------------

    def _recover_stuck(self, stuck_minutes):
        cutoff = timezone.now() - timezone.timedelta(minutes=stuck_minutes)

        for batch in ImportBatch.objects.filter(status="IMPORTING"):
            metadata = batch.metadata if isinstance(batch.metadata, dict) else {}
            claimed = metadata.get(CLAIMED_AT_KEY)

            if not claimed:
                # Claimed before this field existed, or claimed by the old
                # in-request path. Leave it for a human.
                continue

            try:
                claimed_at = timezone.datetime.fromisoformat(claimed)
            except (TypeError, ValueError):
                continue

            if timezone.is_naive(claimed_at):
                claimed_at = timezone.make_aware(claimed_at)

            if claimed_at > cutoff:
                continue

            was_rollback = (
                metadata.get("queued_operation") == "rollback"
            )

            metadata["import_failure"] = (
                "Worker stopped while this "
                f"{'rollback' if was_rollback else 'import'} was running. "
                "The operation was transactional, so nothing was partly "
                "applied. Review and queue it again."
            )

            # A stranded rollback goes back to IMPORTED - the import it was
            # reversing is still in place, and FAILED would claim otherwise.
            ImportBatch.objects.filter(pk=batch.pk).update(
                status="IMPORTED" if was_rollback else "FAILED",
                metadata=metadata,
            )

            self.stderr.write(
                f"Batch #{batch.pk} was stuck in IMPORTING since {claimed}; "
                "marked FAILED."
            )

    # -- the queue -----------------------------------------------------------

    def _claim(self):
        """Claim the oldest queued batch, or return None.

        The conditional UPDATE is the whole concurrency story: two workers
        racing for the same batch both issue it, and exactly one matches a
        row still in QUEUED.
        """

        candidate = (
            ImportBatch.objects
            .filter(status="QUEUED")
            .order_by("created_at", "pk")
            .first()
        )

        if candidate is None:
            return None

        metadata = (
            candidate.metadata
            if isinstance(candidate.metadata, dict)
            else {}
        )
        metadata[CLAIMED_AT_KEY] = timezone.now().isoformat()
        metadata.pop("import_failure", None)

        claimed = (
            ImportBatch.objects
            .filter(pk=candidate.pk, status="QUEUED")
            .update(status="IMPORTING", metadata=metadata)
        )

        if not claimed:
            # Another worker got it between the read and the update.
            return None

        return ImportBatch.objects.get(pk=candidate.pk)

    def _process_one(self):
        batch = self._claim()

        if batch is None:
            return False

        queued_by_id = None

        if isinstance(batch.metadata, dict):
            queued_by_id = batch.metadata.get("queued_by_id")

        user = None

        if queued_by_id:
            from django.contrib.auth import get_user_model

            user = (
                get_user_model().objects
                .filter(pk=queued_by_id)
                .first()
            )

        reconcile = bool(
            isinstance(batch.metadata, dict)
            and batch.metadata.get("queued_reconcile")
        )

        operation = "import"

        if isinstance(batch.metadata, dict):
            operation = batch.metadata.get("queued_operation", "import")

        self.stdout.write(
            f"{operation.title()}ing batch #{batch.pk} "
            f"({batch.source_name})..."
        )

        started = time.perf_counter()

        try:
            if operation == "rollback":
                result = rollback_batch(
                    batch.pk,
                    user=user,
                    # We already own this batch - see _claim().
                    expected_statuses={"IMPORTING"},
                )

            else:
                result = apply_batch(
                    batch.pk,
                    user=user,
                    reconcile=reconcile,
                    expected_statuses={"IMPORTING"},
                )

        except FinalImportError as exc:
            self._record_failure(batch.pk, str(exc))
            self.stderr.write(f"Batch #{batch.pk} failed: {exc}")
            return True

        except Exception as exc:
            self._record_failure(batch.pk, f"{type(exc).__name__}: {exc}")
            self.stderr.write(f"Batch #{batch.pk} failed: {exc}")
            return True

        seconds = time.perf_counter() - started

        if operation == "rollback":
            self.stdout.write(
                self.style.SUCCESS(
                    f"Batch #{batch.pk} rolled back in {seconds:.1f}s "
                    f"({result.get('reversed_changes', 0)} changes "
                    "reversed)."
                )
            )

        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Batch #{batch.pk} imported in {seconds:.1f}s "
                    f"({result.get('processed', 0)} rows, "
                    f"{result.get('created_services', 0)} services created)."
                )
            )

        return True

    def _record_failure(self, batch_id, message):
        """Store why it failed so the admin screen can show it.

        apply_batch already sets FAILED; this only attaches the reason.
        """

        batch = ImportBatch.objects.filter(pk=batch_id).first()

        if batch is None:
            return

        metadata = batch.metadata if isinstance(batch.metadata, dict) else {}
        metadata["import_failure"] = message

        # A rollback that fails must go back to IMPORTED, not FAILED: the
        # import it was reversing is still applied, and FAILED would say the
        # opposite.
        was_rollback = metadata.get("queued_operation") == "rollback"

        ImportBatch.objects.filter(pk=batch_id).update(
            status="IMPORTED" if was_rollback else "FAILED",
            metadata=metadata,
        )
