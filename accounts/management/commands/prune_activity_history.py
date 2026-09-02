"""Delete activity history past its retention window.

Three tables grow with every action and nothing ever removed rows from them:

    accounts.ActivityLog   one row per login, search, view, admin action
    toolkit.SearchEvent    one row per search
    accounts.LoginSession  one row per sign-in

At thirty BDEs doing fifty actions a day that is roughly half a million rows a
year. Left alone it slows the admin activity screens and, more importantly,
inflates the pre-import `pg_dump` that runs inside the import request - the
one place with a hard 120 second timeout.

Security-relevant events (failed and blocked sign-ins, permission denials) are
kept for a longer window than routine browsing, because they are the rows
someone would actually want during an investigation.

Run daily from cron (self-hosted) or a Render cron job:

    manage.py prune_activity_history

Use --dry-run first on a real database to see what would go.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import ActivityLog, LoginSession


# Kept longer than routine activity - these are the rows an investigation
# needs. Mirrors the actions written by accounts/auth_views.py and
# accounts/network_security.py.
SECURITY_ACTIONS = (
    "LOGIN_FAILED",
    "LOGIN_BLOCKED",
    "PERMISSION_DENIED",
)

DEFAULT_DAYS = 365
DEFAULT_SECURITY_DAYS = 730

# Deleting hundreds of thousands of rows in one statement holds a long lock.
# Chunking keeps each transaction short so the app stays responsive.
CHUNK = 5000


class Command(BaseCommand):
    help = "Delete activity history older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=DEFAULT_DAYS,
            help=(
                "Retention window for routine activity "
                f"(default {DEFAULT_DAYS})."
            ),
        )

        parser.add_argument(
            "--security-days",
            type=int,
            default=DEFAULT_SECURITY_DAYS,
            help=(
                "Retention window for failed/blocked sign-ins and permission "
                f"denials (default {DEFAULT_SECURITY_DAYS})."
            ),
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        security_days = options["security_days"]
        dry_run = options["dry_run"]

        if days < 1 or security_days < 1:
            self.stderr.write("Retention windows must be at least 1 day.")
            return

        if security_days < days:
            self.stderr.write(
                "--security-days is shorter than --days, which would delete "
                "security events sooner than routine ones. Refusing."
            )
            return

        now = timezone.now()
        cutoff = now - timedelta(days=days)
        security_cutoff = now - timedelta(days=security_days)

        self.stdout.write(
            f"Routine activity older than {cutoff:%Y-%m-%d} "
            f"({days} days) will be removed."
        )
        self.stdout.write(
            f"Security events older than {security_cutoff:%Y-%m-%d} "
            f"({security_days} days) will be removed."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - nothing deleted.\n"))

        total = 0

        total += self._prune(
            "ActivityLog (routine)",
            ActivityLog.objects
            .filter(created_at__lt=cutoff)
            .exclude(action__in=SECURITY_ACTIONS),
            dry_run,
        )

        total += self._prune(
            "ActivityLog (security)",
            ActivityLog.objects
            .filter(created_at__lt=security_cutoff)
            .filter(action__in=SECURITY_ACTIONS),
            dry_run,
        )

        total += self._prune(
            "LoginSession",
            LoginSession.objects.filter(login_at__lt=cutoff),
            dry_run,
        )

        total += self._prune(
            "SearchEvent",
            self._search_events(cutoff),
            dry_run,
        )

        verb = "would be removed" if dry_run else "removed"
        self.stdout.write(
            self.style.SUCCESS(f"\n{total} rows {verb}.")
        )

    def _search_events(self, cutoff):
        from toolkit.models import SearchEvent

        return SearchEvent.objects.filter(created_at__lt=cutoff)

    def _prune(self, label, queryset, dry_run):
        count = queryset.count()

        if not count:
            self.stdout.write(f"  {label:26} nothing to remove")
            return 0

        if dry_run:
            self.stdout.write(f"  {label:26} {count} rows")
            return count

        removed = 0

        while True:
            # Re-evaluate each pass: slicing a queryset that is being deleted
            # from needs a fresh window, and the id list keeps the DELETE
            # statement bounded.
            ids = list(
                queryset.values_list("pk", flat=True)[:CHUNK]
            )

            if not ids:
                break

            deleted, _ = (
                queryset.model.objects
                .filter(pk__in=ids)
                .delete()
            )

            removed += len(ids)

        self.stdout.write(f"  {label:26} {removed} rows removed")

        return removed
