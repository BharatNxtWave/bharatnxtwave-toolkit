from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from toolkit.intelligence.final_import import (
    FinalImportError,
    rollback_batch,
)


class Command(BaseCommand):

    help = (
        "Rollback one controlled "
        "BharatNXT Toolkit import batch."
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
            "--confirm",
            action="store_true",
        )

    def handle(
        self,
        *args,
        **options,
    ):

        if not options[
            "confirm"
        ]:

            raise CommandError(
                "Refusing to rollback "
                "without --confirm."
            )

        try:

            result = rollback_batch(
                options[
                    "batch_id"
                ]
            )

        except FinalImportError as exc:

            raise CommandError(
                str(exc)
            )

        self.stdout.write(
            self.style.SUCCESS(
                str(result)
            )
        )
