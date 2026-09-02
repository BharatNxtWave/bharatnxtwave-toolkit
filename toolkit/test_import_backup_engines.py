"""Tests for the pre-import safety backup across database engines.

`backup_database` is called unconditionally by `apply_batch` and
`rollback_batch`, so it sits on the live web import path. It used to raise
`FinalImportError` on any engine except SQLite, which meant the entire Final
Import feature failed on the production PostgreSQL database.

The existing import tests never caught this because they patch
`backup_database` out entirely - so they pass on SQLite and say nothing about
production. These tests exercise the real function against each engine.
"""

import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from toolkit.intelligence.final_import import (
    FinalImportError,
    backup_database,
)


SQLITE_ENGINE = "django.db.backends.sqlite3"
POSTGRES_ENGINE = "django.db.backends.postgresql"


class BackupDatabaseEngineTests(SimpleTestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self.backup_root = Path(self._tmp.name) / "audit"

        # These tests never open a connection - they only read
        # settings.DATABASES - so Django's override warning is noise here.
        context = warnings.catch_warnings()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

        warnings.filterwarnings(
            "ignore",
            message="Overriding setting DATABASES",
        )

    def _override(self, databases):
        return override_settings(
            DATABASES=databases,
            BNW_IMPORT_BACKUP_ROOT=self.backup_root,
        )

    # -- PostgreSQL ----------------------------------------------------------

    def _postgres_settings(self):
        return {
            "default": {
                "ENGINE": POSTGRES_ENGINE,
                "NAME": "bharatnxt_toolkit",
                "USER": "bharatnxt_app",
                "PASSWORD": "super-secret-password",
                "HOST": "127.0.0.1",
                "PORT": "5432",
            }
        }

    def test_postgresql_backup_does_not_raise(self):
        """The regression test: this used to raise on PostgreSQL."""

        with self._override(self._postgres_settings()):
            with patch(
                "toolkit.intelligence.final_import.shutil.which",
                return_value="/usr/bin/pg_dump",
            ):
                with patch(
                    "toolkit.intelligence.final_import.subprocess.run"
                ) as run:
                    path = backup_database(42)

        self.assertTrue(run.called)
        self.assertTrue(path.endswith(".dump"))

    def test_postgresql_backup_invokes_pg_dump_with_the_database(self):
        with self._override(self._postgres_settings()):
            with patch(
                "toolkit.intelligence.final_import.shutil.which",
                return_value="/usr/bin/pg_dump",
            ):
                with patch(
                    "toolkit.intelligence.final_import.subprocess.run"
                ) as run:
                    backup_database(7)

        command = run.call_args.args[0]

        self.assertEqual(command[0], "pg_dump")
        self.assertIn("--format=custom", command)
        self.assertIn("bharatnxt_toolkit", command)

    def test_password_is_passed_by_environment_not_argv(self):
        """A password in argv would be visible in the process list."""

        with self._override(self._postgres_settings()):
            with patch(
                "toolkit.intelligence.final_import.shutil.which",
                return_value="/usr/bin/pg_dump",
            ):
                with patch(
                    "toolkit.intelligence.final_import.subprocess.run"
                ) as run:
                    backup_database(7)

        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]

        self.assertNotIn("super-secret-password", " ".join(command))
        self.assertEqual(
            environment["PGPASSWORD"],
            "super-secret-password",
        )

    def test_missing_pg_dump_gives_an_actionable_error(self):
        with self._override(self._postgres_settings()):
            with patch(
                "toolkit.intelligence.final_import.shutil.which",
                return_value=None,
            ):
                with self.assertRaises(FinalImportError) as caught:
                    backup_database(1)

        self.assertIn("pg_dump", str(caught.exception))

    # -- SQLite --------------------------------------------------------------

    def test_sqlite_backup_still_writes_a_file(self):
        source = Path(self._tmp.name) / "db.sqlite3"

        import sqlite3

        connection = sqlite3.connect(str(source))
        connection.execute("CREATE TABLE smoke (id INTEGER)")
        connection.commit()
        connection.close()

        databases = {
            "default": {
                "ENGINE": SQLITE_ENGINE,
                "NAME": str(source),
            }
        }

        with self._override(databases):
            path = backup_database(3)

        self.assertTrue(Path(path).exists())
        self.assertTrue(path.endswith(".sqlite3"))

    # -- anything else -------------------------------------------------------

    def test_unsupported_engine_is_rejected_clearly(self):
        databases = {
            "default": {
                "ENGINE": "django.db.backends.oracle",
                "NAME": "whatever",
            }
        }

        with self._override(databases):
            with self.assertRaises(FinalImportError) as caught:
                backup_database(1)

        self.assertIn("oracle", str(caught.exception))
