"""Tests for the activity-history retention command.

Retention is a destructive operation on the audit trail, so the window
boundaries and the longer security window need to be exact: deleting a
sign-in failure a year too early removes exactly the row an investigation
would want.
"""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import ActivityLog, LoginSession


User = get_user_model()


class PruneActivityHistoryTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="prune_user",
            password="prune-test-password-1234",
            role="BDE",
        )

    def _log(self, action, age_days):
        row = ActivityLog.objects.create(
            user=self.user,
            action=action,
            description=f"{action} at {age_days} days",
        )

        # auto_now_add ignores an assigned value, so rewrite it afterwards.
        ActivityLog.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )

        return row

    def _session(self, age_days):
        row = LoginSession.objects.create(
            user=self.user,
            session_key=f"key-{age_days}",
            is_active=False,
        )

        LoginSession.objects.filter(pk=row.pk).update(
            login_at=timezone.now() - timedelta(days=age_days)
        )

        return row

    def _run(self, **kwargs):
        out = StringIO()
        call_command("prune_activity_history", stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    # -- routine activity ----------------------------------------------------

    def test_old_routine_activity_is_removed(self):
        old = self._log("SEARCH", 400)

        self._run()

        self.assertFalse(
            ActivityLog.objects.filter(pk=old.pk).exists()
        )

    def test_recent_routine_activity_is_kept(self):
        recent = self._log("SEARCH", 30)

        self._run()

        self.assertTrue(
            ActivityLog.objects.filter(pk=recent.pk).exists()
        )

    def test_boundary_row_just_inside_the_window_is_kept(self):
        edge = self._log("SEARCH", 364)

        self._run()

        self.assertTrue(
            ActivityLog.objects.filter(pk=edge.pk).exists(),
            "A row inside the retention window was deleted.",
        )

    # -- security events keep a longer window --------------------------------

    def test_security_events_survive_the_routine_window(self):
        """A failed sign-in at 400 days outlives a search at 400 days."""

        search = self._log("SEARCH", 400)
        failed = self._log("LOGIN_FAILED", 400)
        blocked = self._log("LOGIN_BLOCKED", 400)
        denied = self._log("PERMISSION_DENIED", 400)

        self._run()

        self.assertFalse(ActivityLog.objects.filter(pk=search.pk).exists())

        for row in (failed, blocked, denied):
            self.assertTrue(
                ActivityLog.objects.filter(pk=row.pk).exists(),
                f"Security event {row.action} was deleted too early.",
            )

    def test_security_events_are_removed_past_their_own_window(self):
        ancient = self._log("LOGIN_FAILED", 900)

        self._run()

        self.assertFalse(
            ActivityLog.objects.filter(pk=ancient.pk).exists()
        )

    # -- other tables --------------------------------------------------------

    def test_old_login_sessions_are_removed(self):
        old = self._session(400)
        recent = self._session(10)

        self._run()

        self.assertFalse(LoginSession.objects.filter(pk=old.pk).exists())
        self.assertTrue(LoginSession.objects.filter(pk=recent.pk).exists())

    # -- safety --------------------------------------------------------------

    def test_dry_run_deletes_nothing(self):
        old = self._log("SEARCH", 400)

        output = self._run(dry_run=True)

        self.assertIn("DRY RUN", output)
        self.assertTrue(
            ActivityLog.objects.filter(pk=old.pk).exists(),
            "--dry-run deleted rows.",
        )

    def test_security_window_shorter_than_routine_is_refused(self):
        """Would delete security events sooner than routine ones."""

        old = self._log("LOGIN_FAILED", 400)

        output = self._run(days=365, security_days=30)

        self.assertIn("Refusing", output)
        self.assertTrue(
            ActivityLog.objects.filter(pk=old.pk).exists()
        )

    def test_zero_retention_is_refused(self):
        old = self._log("SEARCH", 400)

        self._run(days=0)

        self.assertTrue(
            ActivityLog.objects.filter(pk=old.pk).exists()
        )

    def test_custom_window_is_honoured(self):
        row = self._log("SEARCH", 60)

        self._run(days=30, security_days=30)

        self.assertFalse(
            ActivityLog.objects.filter(pk=row.pk).exists()
        )
