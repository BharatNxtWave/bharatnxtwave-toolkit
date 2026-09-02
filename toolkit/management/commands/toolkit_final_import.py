from django.core.management.base import BaseCommand, CommandError

from toolkit.importing.execution import (
    preflight,
    rehearse_import,
    rollback_import,
    run_import,
)


class Command(BaseCommand):
    help = "BharatNXT Wave controlled final workbook import."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--preflight", action="store_true")
        group.add_argument("--rehearse", action="store_true")
        group.add_argument("--import", dest="do_import", action="store_true")
        group.add_argument("--rollback", action="store_true")

    def handle(self, *args, **options):
        try:
            if options["preflight"]:
                result = preflight()
            elif options["rehearse"]:
                result = rehearse_import()
            elif options["do_import"]:
                result = run_import()
            elif options["rollback"]:
                result = rollback_import()
            else:
                raise CommandError("No operation selected.")
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("PASS"))
        for key, value in result.items():
            self.stdout.write(f"{key}: {value}")
