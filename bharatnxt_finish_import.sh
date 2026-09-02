#!/usr/bin/env bash
# BharatNXT Wave — final migration, rehearsal, controlled import and verification.
# Run ONLY after bharatnxt_final_import_patch.py prints PATCH COMPLETE.

set -Eeuo pipefail

ROOT='/mnt/d/BharatNXT Wave/BharatNXTwave Toolkit'
cd "$ROOT"

if [[ -x '.venv/bin/python' ]]; then
  PY='.venv/bin/python'
else
  PY='python'
fi

trap 'echo; echo "STOPPED: final import chain failed at line $LINENO."; echo "Do not rerun blindly. Paste the error output into ChatGPT."' ERR

mkdir -p confidential_source/audit/db_backups
STAMP="$(date +%Y%m%d_%H%M%S)"

DB_PATH="$($PY - <<'PY'
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
print(settings.DATABASES['default']['NAME'])
PY
)"

if [[ ! -f "$DB_PATH" ]]; then
  echo "STOP: SQLite database not found: $DB_PATH"
  exit 1
fi

BACKUP="confidential_source/audit/db_backups/db_before_final_import_${STAMP}.sqlite3"
cp -- "$DB_PATH" "$BACKUP"
sha256sum "$BACKUP" | tee "${BACKUP}.sha256"

echo
echo '===== BACKUP CREATED ====='
echo "$BACKUP"

echo
echo '===== PRE-MIGRATION SQLITE INTEGRITY ====='
$PY - "$DB_PATH" <<'PY'
import sqlite3, sys
path = sys.argv[1]
con = sqlite3.connect(path)
try:
    integrity = con.execute('PRAGMA integrity_check;').fetchone()[0]
    fk = con.execute('PRAGMA foreign_key_check;').fetchall()
finally:
    con.close()
print('integrity_check:', integrity)
print('foreign_key_violations:', len(fk))
if integrity != 'ok' or fk:
    raise SystemExit('STOP: database integrity check failed before migration.')
PY

echo
echo '===== DJANGO CHECK ====='
$PY manage.py check

echo
echo '===== APPLY FINAL IMPORT MIGRATION ====='
$PY manage.py migrate toolkit

echo
echo '===== MIGRATION DRIFT CHECK ====='
$PY manage.py makemigrations --check --dry-run

echo
echo '===== FINAL IMPORT PREFLIGHT ====='
$PY manage.py toolkit_final_import --preflight | tee confidential_source/audit/final_import_preflight_SAFE_TO_SHARE.txt

echo
echo '===== FORCED ROLLBACK REHEARSAL ====='
$PY manage.py toolkit_final_import --rehearse | tee confidential_source/audit/final_import_rehearsal_SAFE_TO_SHARE.txt

echo
echo '===== CONTROLLED ATOMIC IMPORT ====='
$PY manage.py toolkit_final_import --import | tee confidential_source/audit/final_import_execution_SAFE_TO_SHARE.txt

echo
echo '===== POST-IMPORT VERIFICATION ====='
$PY manage.py shell <<'PY' | tee confidential_source/audit/final_import_postcheck_SAFE_TO_SHARE.txt
from django.db import connection
from toolkit.models import (
    Category,
    CommunicationTemplate,
    ComparisonEntry,
    ComparisonMatrix,
    ImportBatch,
    ImportChange,
    ImportRow,
    KnowledgeDocument,
    KnowledgeSection,
    ReferenceItem,
    Service,
    ServiceClassification,
    ServiceCommercial,
    ServiceContentSection,
    ServiceSource,
)

batch = ImportBatch.objects.get(pk=5)
rows = ImportRow.objects.filter(import_batch=batch)
changes = ImportChange.objects.filter(import_batch=batch)
created_service_ids = changes.filter(action='SERVICE_CREATE').values_list('object_pk', flat=True)
created_services = Service.objects.filter(pk__in=list(created_service_ids))
rolling = rows.filter(sheet_name='Rolling_Grants')

with connection.cursor() as cursor:
    cursor.execute('PRAGMA integrity_check;')
    integrity = cursor.fetchone()[0]
    cursor.execute('PRAGMA foreign_key_check;')
    fk = cursor.fetchall()

checks = {
    'batch_imported': batch.status == 'IMPORTED',
    'service_total_163': Service.objects.count() == 163,
    'category_total_40': Category.objects.count() == 40,
    'created_services_162': created_services.count() == 162,
    'created_services_all_draft': created_services.exclude(status='DRAFT').count() == 0,
    'staged_rows_478': rows.count() == 478,
    'processed_rows_478': rows.filter(processed_at__isnull=False).count() == 478,
    'rows_with_empty_outcomes_0': sum(1 for r in rows.only('import_outcomes') if not r.import_outcomes) == 0,
    'rolling_rows_7': rolling.count() == 7,
    'rolling_imported_service_7': rolling.filter(imported_service__isnull=False).count() == 7,
    'rolling_merged_5': rolling.filter(matched_service__isnull=False).count() == 5,
    'classification_150': ServiceClassification.objects.count() == 150,
    'commercial_161': ServiceCommercial.objects.count() == 161,
    'commercial_all_admin': ServiceCommercial.objects.exclude(visibility='ADMIN_ONLY').count() == 0,
    'service_content_section_0': ServiceContentSection.objects.count() == 0,
    'knowledge_documents_5': KnowledgeDocument.objects.count() == 5,
    'knowledge_sections_207': KnowledgeSection.objects.count() == 207,
    'knowledge_unlinked_207': KnowledgeSection.objects.filter(linked_service__isnull=True).count() == 207,
    'knowledge_all_admin': KnowledgeSection.objects.exclude(visibility='ADMIN_ONLY').count() == 0,
    'references_all_admin': ReferenceItem.objects.exclude(visibility='ADMIN_ONLY').count() == 0,
    'communication_1': CommunicationTemplate.objects.count() == 1,
    'communication_draft_admin': CommunicationTemplate.objects.filter(status='DRAFT', visibility='ADMIN_ONLY').count() == 1,
    'comparison_matrix_1': ComparisonMatrix.objects.count() == 1,
    'comparison_entries_nonzero': ComparisonEntry.objects.count() > 0,
    'sources_nonzero': ServiceSource.objects.count() > 0,
    'ledger_nonzero': changes.count() > 0,
    'sqlite_integrity_ok': integrity == 'ok',
    'foreign_key_violations_0': len(fk) == 0,
}

print('BHARATNXT WAVE FINAL IMPORT POSTCHECK')
print('====================================')
for name, passed in checks.items():
    print(('PASS' if passed else 'FAIL'), '|', name)

print('')
print('SAFE COUNTS')
print('Services:', Service.objects.count())
print('Categories:', Category.objects.count())
print('ImportRows:', rows.count())
print('ImportChanges:', changes.count())
print('ServiceClassifications:', ServiceClassification.objects.count())
print('ServiceCommercial:', ServiceCommercial.objects.count())
print('ServiceSources:', ServiceSource.objects.count())
print('ReferenceItems:', ReferenceItem.objects.count())
print('ComparisonMatrices:', ComparisonMatrix.objects.count())
print('ComparisonEntries:', ComparisonEntry.objects.count())
print('KnowledgeDocuments:', KnowledgeDocument.objects.count())
print('KnowledgeSections:', KnowledgeSection.objects.count())
print('CommunicationTemplates:', CommunicationTemplate.objects.count())
print('Rolling merged rows:', rolling.filter(matched_service__isnull=False).count())
print('Batch status:', batch.status)
print('integrity_check:', integrity)
print('foreign_key_violations:', len(fk))

failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit('POSTCHECK FAILED: ' + ', '.join(failed))

print('')
print('FINAL_IMPORT_POSTCHECK: PASS')
PY

echo
echo '===== FINAL DJANGO CHECK ====='
$PY manage.py check
$PY manage.py makemigrations --check --dry-run

echo
echo '============================================================'
echo 'BHARATNXT FINAL IMPORT CHAIN: PASS'
echo "DATABASE BACKUP: $BACKUP"
echo 'All imported Services remain DRAFT.'
echo 'Knowledge/reference/commercial/communication data remains ADMIN_ONLY.'
echo 'No BDE rollout has been activated.'
echo '============================================================'
