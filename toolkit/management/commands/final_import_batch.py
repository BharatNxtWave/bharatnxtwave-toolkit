from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from toolkit.intelligence.final_import import (
    DuplicateSourceError,
    FinalImportError,
    apply_batch,
    preview_batch,
)


class Command(BaseCommand):

    help = (
        "Preview or execute a controlled "
        "BharatNXT Toolkit final import."
    )

    def add_arguments(
        self,
        parser,
    ):

        parser.add_argument(
            "batch_id",
            type=int,
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
        )

        parser.add_argument(
            "--reconcile",
            action="store_true",
        )

        parser.add_argument(
            "--confirm",
            action="store_true",
        )

    def handle(
        self,
        *args,
        **options,
    ):

        batch_id = options[
            "batch_id"
        ]

        preview = preview_batch(
            batch_id
        )

        self.stdout.write(
            f"Batch: #{batch_id}"
        )

        self.stdout.write(
            f"Status: "
            f"{preview['status']}"
        )

        self.stdout.write(
            f"Candidate rows: "
            f"{preview['candidate_rows']}"
        )

        self.stdout.write(
            f"Delta counts: "
            f"{preview['delta_counts']}"
        )

        self.stdout.write(
            f"Approved: "
            f"{preview['approved']}"
        )

        self.stdout.write(
            f"Skipped: "
            f"{preview['skipped']}"
        )

        self.stdout.write(
            f"Pending changes: "
            f"{preview['pending_changes']}"
        )

        self.stdout.write(
            f"Duplicate source: "
            f"{preview['duplicate']}"
        )

        if preview[
            "duplicate"
        ]:

            self.stdout.write(
                f"Duplicate of: "
                f"#{preview['duplicate_of']}"
            )

        if options[
            "dry_run"
        ]:

            self.stdout.write(
                self.style.SUCCESS(
                    "DRY RUN ONLY — "
                    "DATABASE WRITES: 0"
                )
            )

            return

        if not options[
            "confirm"
        ]:

            raise CommandError(
                "Refusing to import without "
                "--confirm."
            )

        try:

            result = apply_batch(
                batch_id,
                reconcile=options[
                    "reconcile"
                ],
            )

        except (
            DuplicateSourceError,
            FinalImportError,
        ) as exc:

            raise CommandError(
                str(exc)
            )

        self.stdout.write(
            self.style.SUCCESS(
                str(result)
            )
        )
