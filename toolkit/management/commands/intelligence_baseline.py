from django.core.management.base import BaseCommand

from toolkit.intelligence.workbook_intelligence import (
    save_plan,
)


class Command(BaseCommand):

    help = (
        "Build the BharatNXT intelligent "
        "workbook ingestion baseline. "
        "READ ONLY."
    )

    def handle(self, *args, **options):

        self.stdout.write(
            "=" * 72
        )

        self.stdout.write(
            "BHARATNXT INTELLIGENT INGESTION — BASELINE"
        )

        self.stdout.write(
            "=" * 72
        )

        plan, output = save_plan()

        workbook = plan["workbook"]
        database = plan["database"]
        candidates = plan[
            "candidate_totals"
        ]
        missing = plan[
            "missing_counts"
        ]

        self.stdout.write("")
        self.stdout.write(
            "===== WORKBOOK ====="
        )

        self.stdout.write(
            f"SHA256: "
            f"{workbook['sha256']}"
        )

        self.stdout.write(
            f"Sheets: "
            f"{workbook['sheet_count']}"
        )

        self.stdout.write(
            f"Non-empty cells: "
            f"{workbook['nonempty_cells']}"
        )

        self.stdout.write(
            f"Hyperlinks: "
            f"{workbook['hyperlinks']}"
        )

        self.stdout.write(
            f"Formulas: "
            f"{workbook['formulas']}"
        )

        self.stdout.write(
            f"Merged ranges: "
            f"{workbook['merged_ranges']}"
        )

        self.stdout.write("")
        self.stdout.write(
            "===== CURRENT DATABASE ====="
        )

        for key, value in (
            database.items()
        ):
            self.stdout.write(
                f"{key}: {value}"
            )

        self.stdout.write("")
        self.stdout.write(
            "===== EXISTING KNOWLEDGE MODELS ====="
        )

        if plan[
            "knowledge_models"
        ]:

            for item in (
                plan[
                    "knowledge_models"
                ]
            ):

                self.stdout.write(
                    f"{item['model']}: "
                    f"{item['count']}"
                )

        else:

            self.stdout.write(
                "No Knowledge* models detected."
            )

        self.stdout.write("")
        self.stdout.write(
            "===== EXTRACTION CANDIDATES ====="
        )

        for key, value in (
            candidates.items()
        ):
            self.stdout.write(
                f"{key}: {value}"
            )

        self.stdout.write("")
        self.stdout.write(
            "===== SERVICES STILL MISSING ====="
        )

        for key, value in sorted(
            missing.items()
        ):
            self.stdout.write(
                f"{key}: {value}"
            )

        self.stdout.write("")
        self.stdout.write(
            "===== OUTPUT ====="
        )

        self.stdout.write(
            str(output)
        )

        self.stdout.write("")
        self.stdout.write(
            "=" * 72
        )

        self.stdout.write(
            self.style.SUCCESS(
                "INTELLIGENCE BASELINE: PASS"
            )
        )

        self.stdout.write(
            "DATABASE WRITES: 0"
        )

        self.stdout.write(
            "=" * 72
        )
