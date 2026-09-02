BHARATNXT WAVE — FINAL IMPORT PACKAGE
======================================

IMPORTANT
- Run from the existing project root only.
- Terminal 1 may keep the Django dev server stopped while migrations/import run.
- Terminal 2 is used for these commands.
- The first script changes source code and generates a migration, but DOES NOT apply it or import data.
- The second script creates a database backup, applies the migration, runs preflight, runs a forced rollback rehearsal, performs the controlled atomic import, and verifies the result.
- The second script stops automatically on the first failure.
- Do not rerun a failed step blindly; paste the error into ChatGPT.

PROJECT ROOT
D:\BharatNXT Wave\BharatNXTwave Toolkit
WSL: /mnt/d/BharatNXT Wave/BharatNXTwave Toolkit

FILES
1. bharatnxt_final_import_patch.py
2. bharatnxt_finish_import.sh

RUN
---
Copy both files into the project root, then in Terminal 2:

cd "/mnt/d/BharatNXT Wave/BharatNXTwave Toolkit"
source .venv/bin/activate
set +e
python bharatnxt_final_import_patch.py

Only if the first script ends with:
PATCH COMPLETE
DATABASE MIGRATION APPLIED: NO
LIVE IMPORT STARTED: NO

run:

bash bharatnxt_finish_import.sh

A successful final run ends with:
BHARATNXT FINAL IMPORT CHAIN: PASS

SAFETY BEHAVIOUR
----------------
- Mapping Contract v4 is generated and SHA-pinned.
- Exact source workbook remains unchanged.
- Existing code is backed up before patching.
- SQLite database is copied and SHA256-hashed before migration.
- Migration is statically inspected before it can be used.
- Real import is transaction.atomic.
- Forced rollback rehearsal must pass before the real import starts.
- Every staged ImportRow receives explicit outcomes.
- All seven Rolling_Grants rows are accounted for: five merge lineage + two new Services.
- Five knowledge sheets / 207 rows are preserved as dedicated KnowledgeDocument/KnowledgeSection records.
- No fuzzy knowledge-to-Service link is used.
- All imported Services remain DRAFT.
- Knowledge, references, commercial terms and communication templates remain ADMIN_ONLY during this controlled import.

FILE SHA256
-----------
bharatnxt_final_import_patch.py
bbcbe365aa0b535f4ebae8cc26c396b3c0384d9e49c9b369597c5cb43bbdafdc

bharatnxt_finish_import.sh
3e5f5802874f61ea45585ad3136e86bf293196055b9e41a557ba4c8f4943fb97
