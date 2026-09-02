import json

from datetime import datetime
from pathlib import Path

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from toolkit.intelligence.ingestion import (
    analyse_file,
)

from toolkit.models import (
    ImportBatch,
    ImportRow,
    Service,
)


class Command(BaseCommand):

    help = (
        "Read-only intelligent preview "
        "of an XLSX/CSV source."
    )

    def add_arguments(
        self,
        parser,
    ):

        parser.add_argument(
            "path"
        )

    def handle(
        self,
        *args,
        **options,
    ):

        path = Path(
            options[
                "path"
            ]
        )

        if not path.is_file():

            raise CommandError(
                f"File not found: {path}"
            )

        if path.suffix.lower() not in {
            ".xlsx",
            ".csv",
        }:

            raise CommandError(
                "Only .xlsx and .csv files are supported."
            )

        before = (
            Service.objects.count(),
            ImportBatch.objects.count(),
            ImportRow.objects.count(),
        )

        with path.open(
            "rb"
        ) as handle:

            report = analyse_file(
                handle,
                path.name,
            )

        after = (
            Service.objects.count(),
            ImportBatch.objects.count(),
            ImportRow.objects.count(),
        )

        if before != after:

            raise CommandError(
                "Safety failure: "
                "database counts changed."
            )

        audit = Path(
            "confidential_source/audit"
        )

        audit.mkdir(
            parents=True,
            exist_ok=True,
        )

        stamp = (
            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        output = (
            audit
            / (
                "intelligent_ingest_preview_"
                f"{stamp}.json"
            )
        )

        output.write_text(
            json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        self.stdout.write(
            "=" * 72
        )

        self.stdout.write(
            "BHARATNXT — INTELLIGENT "
            "FILE INGESTION PREVIEW"
        )

        self.stdout.write(
            "=" * 72
        )

        self.stdout.write(
            f"Source: "
            f"{report['source_type']}"
        )

        self.stdout.write(
            f"Sheets: "
            f"{report['sheet_count']}"
        )

        self.stdout.write(
            f"Sheet types: "
            f"{report['sheet_type_counts']}"
        )

        self.stdout.write(
            f"Service candidates: "
            f"{report['candidate_count']}"
        )

        self.stdout.write(
            f"Actions: "
            f"{report['candidate_action_counts']}"
        )

        self.stdout.write("")

        self.stdout.write(
            "===== SHEETS ====="
        )

        for sheet in report[
            "sheets"
        ]:

            self.stdout.write(
                f"{sheet['name']} | "
                f"{sheet['kind']} | "
                f"rows="
                f"{sheet['nonempty_rows']} | "
                f"header="
                f"{sheet['header_row']} | "
                f"candidates="
                f"{sheet['candidate_count']}"
            )

        self.stdout.write("")

        self.stdout.write(
            f"Report: {output}"
        )

        self.stdout.write(
            "DATABASE WRITES: 0"
        )

        self.stdout.write(
            self.style.SUCCESS(
                "INTELLIGENT INGESTION "
                "PREVIEW: PASS"
            )
        )
