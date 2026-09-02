#!/usr/bin/env python3
"""BharatNXT Wave final import architecture patch.

Run from the Django project root. This patch DOES NOT apply migrations and
DOES NOT import workbook data. It creates backups, adds the final import
architecture, generates migration 0005, and runs static Django checks.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
MODELS = ROOT / "toolkit" / "models.py"
IMPORTING = ROOT / "toolkit" / "importing"
MANAGEMENT = ROOT / "toolkit" / "management"
COMMANDS = MANAGEMENT / "commands"
AUDIT = ROOT / "confidential_source" / "audit"

REQUIRED = [
    MODELS,
    IMPORTING / "transformation.py",
    IMPORTING / "supporting_transformation.py",
    ROOT / "manage.py",
]

for path in REQUIRED:
    if not path.exists():
        raise SystemExit(f"STOP: required file missing: {path}")

stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = AUDIT / f"final_import_patch_backup_{stamp}"
backup_dir.mkdir(parents=True, exist_ok=False)

for path in REQUIRED[:-1]:
    shutil.copy2(path, backup_dir / path.name)

print(f"SOURCE BACKUP: {backup_dir}")

# ---------------------------------------------------------------------------
# Mapping Contract v4
# ---------------------------------------------------------------------------
CONTRACT_V4 = {
    "contract": {
        "version": 4,
        "name": "BharatNXT Wave Final Import Contract",
        "source_contract_version": 3,
        "batch_id": 5,
        "expected_staged_rows": 478,
        "expected_services": 162,
        "expected_new_categories": 8,
        "expected_classifications": 150,
        "expected_commercial_records": 161,
        "expected_knowledge_documents": 5,
        "expected_knowledge_rows": 207,
        "rules": [
            "Preserve structured benefits, eligibility, funding organisation, applicable-for and raw deadline on Service.",
            "Normalize application_deadline only from a single confidently typed Excel date; otherwise preserve raw and use conservative status.",
            "Preserve all seven Rolling_Grants rows: two new Services and five merge-lineage rows.",
            "Do not use fuzzy knowledge-to-Service attachment.",
            "Preserve all five knowledge sheets as KnowledgeDocument with one KnowledgeSection per staged source row.",
            "Service links from KnowledgeSection remain null unless separately verified.",
            "Preserve non-URL source text rather than discarding it.",
            "All imported Services remain DRAFT.",
            "All newly imported generic knowledge/reference content remains ADMIN_ONLY until release.",
            "Every staged ImportRow must receive one or more explicit import outcomes.",
            "Final write execution must be transaction.atomic and ledgered in ImportChange.",
            "Rollback must reverse ledgered object creation in reverse order.",
        ],
    }
}

contract_text = json.dumps(
    CONTRACT_V4,
    sort_keys=True,
    indent=2,
    ensure_ascii=False,
) + "\n"
contract_hash = hashlib.sha256(contract_text.encode("utf-8")).hexdigest()
EXPECTED_V4_HASH = "9e0112ef3c4189c3f8009bff368d3d1716fb9987098e1ec7460ae0915ebb285c"

if contract_hash != EXPECTED_V4_HASH:
    raise SystemExit("STOP: internal Contract v4 hash mismatch.")

contract_path = AUDIT / "step13_mapping_contract_v4.json"
contract_sha_path = AUDIT / "step13_mapping_contract_v4.sha256"
contract_path.write_text(contract_text, encoding="utf-8")
contract_sha_path.write_text(
    f"{contract_hash}  {contract_path.name}\n",
    encoding="utf-8",
)

# ---------------------------------------------------------------------------
# models.py targeted patch
# ---------------------------------------------------------------------------
models_text = MODELS.read_text(encoding="utf-8")

if "import_outcomes = models.JSONField(" not in models_text:
    marker = '''    processed_at = models.DateTimeField(
        null=True,
        blank=True
    )
'''
    addition = '''
    # Explicit source-row accounting after the controlled workbook import.
    # One source row may legitimately produce multiple outcomes.
    import_outcomes = models.JSONField(
        default=list,
        blank=True
    )
'''
    if marker not in models_text:
        raise SystemExit("STOP: ImportRow processed_at block not found.")
    models_text = models_text.replace(marker, marker + addition, 1)

# Add generic object identity to the existing ledger.
if "object_model = models.CharField(" not in models_text:
    marker = '''    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        db_index=True
    )
'''
    addition = '''
    # Generic destination identity makes every created object reversible,
    # including Categories, comparisons, knowledge and communications.
    object_model = models.CharField(
        max_length=120,
        blank=True
    )

    object_pk = models.CharField(
        max_length=80,
        blank=True
    )
'''
    if marker not in models_text:
        raise SystemExit("STOP: ImportChange action block not found.")
    models_text = models_text.replace(marker, marker + addition, 1)

if "class KnowledgeDocument(models.Model):" not in models_text:
    models_text += '''

# ============================================================
# KNOWLEDGE DOCUMENTS
# Dedicated storage for source knowledge that is not safely attributable
# to one Service. Service linkage is deliberately optional.
# ============================================================

class KnowledgeDocument(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("ACTIVE", "Active"),
        ("ARCHIVED", "Archived"),
    ]

    VISIBILITY_CHOICES = [
        ("ADMIN_ONLY", "Admin Only"),
        ("BDE", "BDE"),
    ]

    document_key = models.CharField(
        max_length=180,
        unique=True
    )

    title = models.CharField(
        max_length=255
    )

    source_sheet = models.CharField(
        max_length=255,
        db_index=True
    )

    source_import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_documents"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
        db_index=True
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="ADMIN_ONLY",
        db_index=True
    )

    metadata = models.JSONField(
        default=dict,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["title", "id"]

    def __str__(self):
        return self.title


class KnowledgeSection(models.Model):

    SECTION_TYPE_CHOICES = [
        ("OVERVIEW", "Overview"),
        ("BENEFITS", "Benefits"),
        ("ELIGIBILITY", "Eligibility"),
        ("FUNDING", "Funding"),
        ("SCOPE", "Scope of Work"),
        ("PROCESS", "Process"),
        ("DOCUMENTS", "Documents"),
        ("TIMELINE", "Timeline"),
        ("NOTES", "Notes"),
        ("GLOSSARY", "Glossary"),
        ("COMMERCIAL", "Commercial"),
        ("OTHER", "Other"),
    ]

    VISIBILITY_CHOICES = [
        ("ADMIN_ONLY", "Admin Only"),
        ("BDE", "BDE"),
    ]

    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="sections"
    )

    linked_service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_sections"
    )

    section_type = models.CharField(
        max_length=20,
        choices=SECTION_TYPE_CHOICES,
        default="OTHER",
        db_index=True
    )

    title = models.CharField(
        max_length=255,
        blank=True
    )

    content = models.TextField()

    display_order = models.PositiveIntegerField(
        default=0
    )

    is_heading = models.BooleanField(
        default=False
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="ADMIN_ONLY",
        db_index=True
    )

    source_import_row = models.OneToOneField(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_section"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["document", "display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "display_order"],
                name="unique_knowledge_section_order_per_document"
            )
        ]

    def __str__(self):
        return (
            f"{self.document.title} - "
            f"{self.title or self.section_type}"
        )
'''

MODELS.write_text(models_text, encoding="utf-8")

# ---------------------------------------------------------------------------
# final_plan.py
# ---------------------------------------------------------------------------
final_plan = r'''"""BharatNXT Wave final production import planner (no DB writes)."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from toolkit.importing.transformation import (
    build_core_transformation_plan,
    column_value,
    fields,
    load_verified_context,
    normalize_identity,
    payload_value,
)
from toolkit.importing.supporting_transformation import (
    KNOWLEDGE_SHEETS,
    build_communication_plan,
    build_comparison_plan,
    build_reference_items,
    build_service_sources,
    find_verified_workbook,
    infer_section_type,
    knowledge_heading_rows,
    row_text,
)
from toolkit.models import KnowledgeSection, Service

EXPECTED_V4_HASH = "9e0112ef3c4189c3f8009bff368d3d1716fb9987098e1ec7460ae0915ebb285c"
CONTRACT_V4_PATH = Path(
    "confidential_source/audit/step13_mapping_contract_v4.json"
)
EXPECTED_STAGED_ROWS = 478
EXPECTED_SERVICES = 162
EXPECTED_ROLLING_ROWS = 7
EXPECTED_KNOWLEDGE_ROWS = 207
EXPECTED_KNOWLEDGE_DOCUMENTS = 5


def _verify_v4_contract():
    if not CONTRACT_V4_PATH.exists():
        raise RuntimeError("Mapping Contract v4 is missing.")
    digest = hashlib.sha256(CONTRACT_V4_PATH.read_bytes()).hexdigest()
    if digest != EXPECTED_V4_HASH:
        raise RuntimeError("Mapping Contract v4 SHA-256 changed.")
    payload = json.loads(CONTRACT_V4_PATH.read_text(encoding="utf-8"))
    if payload.get("contract", {}).get("version") != 4:
        raise RuntimeError("Mapping Contract v4 version mismatch.")
    return payload


def _canonical_field_keys(staged_rows):
    keys = set()
    for row in staged_rows:
        if row.raw_data.get("_meta", {}).get("family") == "SCHEME_TABLE":
            keys.update(fields(row).keys())
    return keys


def _resolve_key(available, explicit, token_groups=()):
    for key in explicit:
        if key in available:
            return key
    normalized = {
        key: re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
        for key in available
    }
    candidates = []
    for key, text in normalized.items():
        for required in token_groups:
            if all(token in text for token in required):
                candidates.append(key)
                break
    candidates = sorted(set(candidates))
    return candidates[0] if len(candidates) == 1 else None


def _business_key_map(staged_rows):
    available = _canonical_field_keys(staged_rows)
    mapping = {
        "benefits": _resolve_key(
            available,
            ("benefits", "benefit"),
            (("benefit",),),
        ),
        "eligibility": _resolve_key(
            available,
            ("eligibility", "eligibility_criteria"),
            (("eligib",),),
        ),
        "funding_organisation": _resolve_key(
            available,
            ("funding_organisation", "funding_organization", "funding_org"),
            (("fund", "org"), ("fund", "agency"), ("fund", "institution")),
        ),
        "applicable_for": _resolve_key(
            available,
            ("applicable_for", "applicable", "who_can_apply"),
            (("applicable",), ("who", "apply")),
        ),
        "deadline": _resolve_key(
            available,
            (
                "deadline",
                "application_deadline",
                "last_date",
                "last_date_to_apply",
                "closing_date",
            ),
            (("deadline",), ("last", "date"), ("closing", "date")),
        ),
        "additional_info": _resolve_key(
            available,
            ("additional_info", "additional_information"),
            (("additional", "info"),),
        ),
    }
    required = (
        "benefits",
        "eligibility",
        "funding_organisation",
        "applicable_for",
        "deadline",
    )
    missing = [name for name in required if mapping[name] is None]
    if missing:
        raise RuntimeError(
            "Business-field mapping unresolved for: "
            + ", ".join(missing)
            + ". Available staged field keys: "
            + ", ".join(sorted(available))
        )
    return mapping


def _payload(row, key):
    if not key:
        return {}
    payload = fields(row).get(key, {})
    return payload if isinstance(payload, dict) else {}


def _distinct_values(group, key, *, skip_certgem_f7=False):
    values = []
    seen = set()
    for row in sorted(group, key=lambda r: (r.sheet_name, r.source_row_number, r.id)):
        payload = _payload(row, key)
        if skip_certgem_f7 and row.sheet_name == "CERTGEM":
            coordinate = str(payload.get("coordinate") or "").upper()
            merged_from = str(payload.get("merged_from") or "").upper()
            if coordinate == "F7" or merged_from == "F7":
                continue
        value = payload_value(payload)
        if not value:
            continue
        value = re.sub(r"\s+", " ", value).strip()
        marker = value.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        values.append((row, value, payload))
    return values


def _merge_text(values):
    return "\n\n---\n\n".join(value for row, value, payload in values)


def _merge_short(values, max_length):
    joined = " | ".join(value for row, value, payload in values)
    if len(joined) > max_length:
        raise RuntimeError(
            f"Preserved source value exceeds destination max_length={max_length}; "
            "automatic truncation is forbidden."
        )
    return joined


def _deadline_status(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    if not text:
        return "UNKNOWN"
    if "rolling" in text:
        return "ROLLING"
    if "ongoing" in text or "on going" in text:
        return "ONGOING"
    if re.search(r"\bopen\b", text):
        return "OPEN"
    if re.search(r"\bclosed\b|\bclose\b", text):
        return "CLOSED"
    if "no deadline" in text or "no last date" in text:
        return "NO_DEADLINE"
    return "OTHER"


def _confident_date(payload):
    if not isinstance(payload, dict) or payload.get("cell_type") != "d":
        return None
    value = payload.get("value")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None


def _fix_rolling_lineage(core, staged_rows):
    rolling = [row for row in staged_rows if row.sheet_name == "Rolling_Grants"]
    if len(rolling) != EXPECTED_ROLLING_ROWS:
        raise RuntimeError("Expected exactly seven Rolling_Grants rows.")
    covered = set()
    merged = 0
    new = 0
    for row in rolling:
        identity = normalize_identity(column_value(row, "A"))
        if not identity or identity not in core["services"]:
            raise RuntimeError(
                "A Rolling_Grants row does not resolve to one of the final 162 Service identities."
            )
        plan = core["services"][identity]
        if row.id not in plan["source_row_ids"]:
            plan["source_row_ids"].append(row.id)
        covered.add(row.id)
        if plan.get("source_family") == "ROLLING_GRANTS":
            new += 1
        else:
            merged += 1
            plan.setdefault("rolling_merge_row_ids", []).append(row.id)
    if len(covered) != 7 or merged != 5 or new != 2:
        raise RuntimeError(
            f"Rolling_Grants contract failed: covered={len(covered)}, merged={merged}, new={new}"
        )
    return {"covered": 7, "merged": 5, "new": 2}


def _enrich_structured_services(core, staged_rows):
    key_map = _business_key_map(staged_rows)
    rows_by_id = {row.id: row for row in staged_rows}
    funding_max = Service._meta.get_field("funding_organisation").max_length or 255
    populated = Counter()

    for identity, plan in core["services"].items():
        if plan.get("source_family") != "STRUCTURED":
            continue
        group = [rows_by_id[rid] for rid in plan["source_row_ids"] if rid in rows_by_id]

        benefits = _distinct_values(group, key_map["benefits"])
        eligibility = _distinct_values(group, key_map["eligibility"])
        funding_org = _distinct_values(
            group,
            key_map["funding_organisation"],
            skip_certgem_f7=True,
        )
        applicable = _distinct_values(group, key_map["applicable_for"])
        deadlines = _distinct_values(group, key_map["deadline"])
        additional = _distinct_values(group, key_map["additional_info"])

        plan["benefits"] = _merge_text(benefits)
        plan["eligibility_summary"] = _merge_text(eligibility)
        plan["funding_organisation"] = _merge_short(funding_org, funding_max)
        plan["applicable_for_raw"] = _merge_text(applicable)
        plan["application_deadline_raw"] = _merge_text(deadlines)
        plan["important_notes"] = _merge_text(additional)

        for name, value in (
            ("benefits", plan["benefits"]),
            ("eligibility", plan["eligibility_summary"]),
            ("funding_organisation", plan["funding_organisation"]),
            ("applicable_for", plan["applicable_for_raw"]),
            ("deadline", plan["application_deadline_raw"]),
        ):
            if value:
                populated[name] += 1

        dates = sorted({
            parsed
            for row, raw_value, payload in deadlines
            for parsed in [_confident_date(payload)]
            if parsed is not None
        })
        statuses = {
            _deadline_status(raw_value)
            for row, raw_value, payload in deadlines
        }

        if len(deadlines) == 1 and len(dates) == 1:
            plan["application_deadline"] = dates[0]
            plan["deadline_status"] = "DATED"
        else:
            plan["application_deadline"] = None
            non_unknown = {s for s in statuses if s != "UNKNOWN"}
            if len(non_unknown) == 1:
                plan["deadline_status"] = next(iter(non_unknown))
            elif deadlines:
                plan["deadline_status"] = "OTHER"
            else:
                plan["deadline_status"] = "UNKNOWN"

    missing_population = [
        name
        for name in (
            "benefits",
            "eligibility",
            "funding_organisation",
            "applicable_for",
            "deadline",
        )
        if populated[name] == 0
    ]
    if missing_population:
        raise RuntimeError(
            "Business-field preservation found zero populated structured Services for: "
            + ", ".join(missing_population)
        )
    return {
        "resolved_keys": key_map,
        "populated_service_counts": dict(populated),
    }


def _build_safe_sources(core, staged_rows):
    result = build_service_sources(core, staged_rows)
    rows_by_id = {row.id: row for row in staged_rows}
    source_fields = {
        "portal_link": ("APPLICATION", "Application / Portal"),
        "flyer": ("FLYER", "Flyer"),
        "additional_info": ("REFERENCE", "Additional Reference"),
    }
    existing_keys = {
        (
            item["service_identity"],
            item["import_row_id"],
            item["source_kind"],
        )
        for item in result["plans"]
    }

    # Preserve hyperlink display text as notes on URL-backed source records.
    # The earlier supporting planner kept the URL but intentionally left
    # notes blank, which is not sufficient for a lossless final import.
    for item in result["plans"]:
        row = rows_by_id.get(item.get("import_row_id"))
        if row is None:
            continue
        reference = str(item.get("source_reference") or "")
        field_name = reference.rsplit(":", 1)[-1] if ":" in reference else ""
        if field_name not in source_fields:
            continue
        visible_text = payload_value(fields(row).get(field_name, {}))
        if visible_text and visible_text != item.get("source_url", ""):
            item["notes"] = visible_text

    added = 0
    for identity, plan in core["services"].items():
        if plan.get("source_family") != "STRUCTURED":
            continue
        for row_id in plan["source_row_ids"]:
            row = rows_by_id.get(row_id)
            if row is None or row.raw_data.get("_meta", {}).get("family") != "SCHEME_TABLE":
                continue
            for field_name, (source_kind, source_name) in source_fields.items():
                payload = fields(row).get(field_name, {})
                value = payload_value(payload)
                if not value:
                    continue
                key = (identity, row.id, source_kind)
                if key in existing_keys:
                    continue
                result["plans"].append({
                    "service_identity": identity,
                    "source_name": source_name,
                    "source_url": "",
                    "source_kind": source_kind,
                    "import_row_id": row.id,
                    "source_reference": f"{row.sheet_name}:{row.source_row_number}:{field_name}",
                    "is_official": False,
                    "notes": value,
                    "extraction_method": "TEXT_ONLY_PRESERVED",
                })
                existing_keys.add(key)
                added += 1
    result["text_only_preserved"] = added
    return result


def _build_knowledge(staged_rows):
    workbook_path = find_verified_workbook()
    headings = knowledge_heading_rows(workbook_path, staged_rows)
    section_choices = {
        str(value)
        for value, label
        in KnowledgeSection._meta.get_field("section_type").choices
    }
    documents = []
    sections = []
    covered = set()

    for sheet_name in KNOWLEDGE_SHEETS:
        rows = sorted(
            [row for row in staged_rows if row.sheet_name == sheet_name],
            key=lambda row: (row.source_row_number, row.id),
        )
        if not rows:
            raise RuntimeError(f"Knowledge sheet has no staged rows: {sheet_name}")
        key = "batch-5-" + re.sub(r"[^a-z0-9]+", "-", sheet_name.casefold()).strip("-")
        documents.append({
            "document_key": key,
            "title": sheet_name.replace("_", " ").strip(),
            "source_sheet": sheet_name,
            "source_import_batch_id": 5,
            "status": "DRAFT",
            "visibility": "ADMIN_ONLY",
            "metadata": {
                "source_row_count": len(rows),
                "service_link_policy": "UNLINKED_UNLESS_VERIFIED",
            },
        })
        current_type = "OTHER"
        for order, row in enumerate(rows, start=1):
            text = row_text(row)
            if not text:
                raise RuntimeError("Knowledge ImportRow unexpectedly contains no staged text.")
            is_heading = row.source_row_number in headings.get(sheet_name, set())
            title = ""
            if is_heading:
                current_type = infer_section_type(text, section_choices)
                if len(text) <= 255:
                    title = text
            sections.append({
                "document_key": key,
                "linked_service_identity": None,
                "section_type": current_type,
                "title": title,
                "content": text,
                "display_order": order,
                "is_heading": is_heading,
                "visibility": "ADMIN_ONLY",
                "source_import_row_id": row.id,
                "source_sheet": sheet_name,
            })
            covered.add(row.id)

    if len(documents) != EXPECTED_KNOWLEDGE_DOCUMENTS:
        raise RuntimeError("Expected five KnowledgeDocument plans.")
    if len(sections) != EXPECTED_KNOWLEDGE_ROWS or len(covered) != EXPECTED_KNOWLEDGE_ROWS:
        raise RuntimeError("Expected exact 207-row knowledge preservation.")
    return {
        "documents": documents,
        "sections": sections,
        "covered_row_ids": sorted(covered),
    }


def _build_outcomes(core, sources, references, comparison, knowledge, communication, staged_rows):
    outcomes = defaultdict(set)

    for identity, plan in core["services"].items():
        merge_rows = set(plan.get("rolling_merge_row_ids", []))
        for row_id in plan["source_row_ids"]:
            outcomes[row_id].add("MERGE" if row_id in merge_rows else "IMPORT")

    for item in core["classifications"]:
        row_id = item.get("source_import_row_id")
        if row_id:
            outcomes[row_id].add("CLASSIFICATION")

    for item in core["commercial"]:
        row_id = item.get("source_import_row_id")
        if row_id:
            outcomes[row_id].add("COMMERCIAL")

    for item in sources["plans"]:
        row_id = item.get("import_row_id")
        if row_id:
            outcomes[row_id].add("SOURCE")

    for item in references:
        row_id = item.get("source_import_row_id")
        if row_id:
            outcomes[row_id].add("REFERENCE")

    for row in staged_rows:
        if row.sheet_name == "LOAN":
            outcomes[row.id].add("COMPARISON")

    for row_id in knowledge["covered_row_ids"]:
        outcomes[row_id].add("KNOWLEDGE")

    for row in staged_rows:
        if row.sheet_name == communication["source_sheet"]:
            outcomes[row.id].add("COMMUNICATION")

    for row in staged_rows:
        if row.validation_status == "INVALID":
            outcomes[row.id].add("INTENTIONALLY_INVALID")

    # Explicit preservation is allowed only for non-scheme, non-knowledge,
    # non-rolling source rows. This prevents a missing core mapping from being
    # hidden behind PRESERVE_ONLY.
    for row in staged_rows:
        if outcomes[row.id]:
            continue
        family = row.raw_data.get("_meta", {}).get("family")
        if family in {"SCHEME_TABLE", "KNOWLEDGE", "ROLLING_GRANTS"}:
            raise RuntimeError(
                f"Critical source row is unaccounted: sheet={row.sheet_name}, row={row.source_row_number}"
            )
        outcomes[row.id].add("PRESERVE_ONLY")

    if len(outcomes) != EXPECTED_STAGED_ROWS:
        raise RuntimeError("478-row outcome reconciliation failed.")

    preserve_by_sheet = Counter(
        row.sheet_name
        for row in staged_rows
        if "PRESERVE_ONLY" in outcomes[row.id]
    )

    return (
        {row_id: sorted(values) for row_id, values in outcomes.items()},
        dict(sorted(preserve_by_sheet.items())),
    )


def build_final_import_plan():
    _verify_v4_contract()
    contract_v3, batch, staged_rows = load_verified_context()
    core = build_core_transformation_plan()
    if len(core["services"]) != EXPECTED_SERVICES:
        raise RuntimeError("Core planner no longer produces 162 Services.")

    rolling = _fix_rolling_lineage(core, staged_rows)
    business = _enrich_structured_services(core, staged_rows)
    sources = _build_safe_sources(core, staged_rows)

    references = build_reference_items(staged_rows)
    # Prevent partial BDE rollout during controlled import.
    for item in references:
        original = item.get("visibility", "ADMIN_ONLY")
        item.setdefault("metadata", {})["release_visibility"] = original
        item["visibility"] = "ADMIN_ONLY"

    comparison = build_comparison_plan(staged_rows)
    knowledge = _build_knowledge(staged_rows)
    communication = build_communication_plan(staged_rows)
    communication["visibility"] = "ADMIN_ONLY"
    communication["status"] = "DRAFT"

    outcomes, preserve_by_sheet = _build_outcomes(
        core,
        sources,
        references,
        comparison,
        knowledge,
        communication,
        staged_rows,
    )

    return {
        "contract_version": 4,
        "source_contract_version": core["contract_version"],
        "batch_id": batch.id,
        "staged_row_count": len(staged_rows),
        "core": core,
        "sources": sources,
        "references": references,
        "comparison": comparison,
        "knowledge": knowledge,
        "communication": communication,
        "row_outcomes": outcomes,
        "preserve_only_by_sheet": preserve_by_sheet,
        "business_field_audit": business,
        "rolling_lineage_audit": rolling,
    }
'''

(IMPORTING / "final_plan.py").write_text(final_plan, encoding="utf-8")

# ---------------------------------------------------------------------------
# execution.py
# ---------------------------------------------------------------------------
execution = r'''"""Atomic BharatNXT Wave controlled import and rollback engine."""

from __future__ import annotations

from copy import deepcopy

from django.apps import apps
from django.db import connection, transaction
from django.utils import timezone

from toolkit.importing.final_plan import build_final_import_plan
from toolkit.importing.transformation import load_verified_context
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
    ServiceDomain,
    ServiceSource,
)

EXPECTED_BASELINE = {
    "Service": 1,
    "Category": 32,
    "ImportRow": 478,
    "ImportChange": 0,
    "ServiceClassification": 0,
    "ServiceCommercial": 0,
    "ServiceSource": 0,
    "ServiceContentSection": 0,
    "ReferenceItem": 0,
    "ComparisonMatrix": 0,
    "ComparisonEntry": 0,
    "CommunicationTemplate": 0,
    "KnowledgeDocument": 0,
    "KnowledgeSection": 0,
}


def _count(name):
    return apps.get_model("toolkit", name).objects.count()


def baseline_counts():
    return {name: _count(name) for name in EXPECTED_BASELINE}


def assert_preimport_baseline():
    actual = baseline_counts()
    if actual != EXPECTED_BASELINE:
        raise RuntimeError(
            f"Pre-import database baseline changed. Expected={EXPECTED_BASELINE}; Actual={actual}"
        )
    return actual


def database_integrity():
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA integrity_check;")
        integrity = cursor.fetchone()
        cursor.execute("PRAGMA foreign_key_check;")
        fk_rows = cursor.fetchall()
    result = integrity[0] if integrity else "NO RESULT"
    if result != "ok" or fk_rows:
        raise RuntimeError(
            f"SQLite integrity failed: integrity={result}, foreign_keys={len(fk_rows)}"
        )
    return {"integrity_check": result, "foreign_key_violations": 0}


def _record_change(*, batch, action, obj, import_row=None, service=None):
    return ImportChange.objects.create(
        import_batch=batch,
        import_row=import_row,
        service=service,
        action=action,
        object_model=obj._meta.label,
        object_pk=str(obj.pk),
        before_snapshot={},
        after_snapshot={"model": obj._meta.label, "pk": str(obj.pk)},
    )


def _resolve_categories(plan, batch):
    domains = {obj.slug: obj for obj in ServiceDomain.objects.all()}
    category_map = {
        (obj.domain.slug, obj.slug): obj
        for obj in Category.objects.select_related("domain").all()
    }
    created = []
    for item in plan["core"]["categories"]:
        pair = (item["domain_slug"], item["slug"])
        if pair in category_map:
            raise RuntimeError(f"Planned Category unexpectedly already exists: {pair}")
        domain = domains.get(item["domain_slug"])
        if domain is None:
            raise RuntimeError("Planned Category references a missing domain.")
        obj = Category.objects.create(
            domain=domain,
            name=item["name"],
            slug=item["slug"],
            description=item.get("description", ""),
            display_order=item.get("display_order", 0),
            is_active=True,
        )
        category_map[pair] = obj
        created.append(obj)
        _record_change(batch=batch, action="OTHER", obj=obj)
    return category_map, created


def _service_kwargs(item, category_map):
    pair = (item["domain_slug"], item["category_slug"])
    category = category_map.get(pair)
    if category is None:
        raise RuntimeError(f"Service primary category unavailable: {pair}")
    return {
        "service_id": item["service_id"],
        "title": item["title"],
        "slug": item["slug"],
        "domain": category.domain,
        "category": category,
        "service_kind": item["service_kind"],
        "status": "DRAFT",
        "priority": item.get("priority", "NORMAL"),
        "benefits": item.get("benefits", ""),
        "eligibility_summary": item.get("eligibility_summary", ""),
        "funding_organisation": item.get("funding_organisation", ""),
        "applicable_for_raw": item.get("applicable_for_raw", ""),
        "application_deadline_raw": item.get("application_deadline_raw", ""),
        "application_deadline": item.get("application_deadline"),
        "deadline_status": item.get("deadline_status", "UNKNOWN"),
        "important_notes": item.get("important_notes", ""),
    }


def _execute(plan):
    contract_v3, batch, staged_rows = load_verified_context()
    if batch.pk != plan["batch_id"] or batch.status != "PREVIEWED":
        raise RuntimeError(
            f"Batch #{batch.pk} must be PREVIEWED before import; current={batch.status}"
        )
    if ImportChange.objects.filter(import_batch=batch).exists():
        raise RuntimeError("Batch already has ImportChange rows.")

    batch.status = "IMPORTING"
    batch.save(update_fields=["status"])

    category_map, created_categories = _resolve_categories(plan, batch)
    service_map = {}

    for identity, item in plan["core"]["services"].items():
        obj = Service.objects.create(**_service_kwargs(item, category_map))
        service_map[identity] = obj
        _record_change(
            batch=batch,
            action="SERVICE_CREATE",
            obj=obj,
            service=obj,
        )

    rows_by_id = {row.id: row for row in staged_rows}

    for item in plan["core"]["classifications"]:
        service = service_map[item["service_identity"]]
        pair = (item["domain_slug"], item["category_slug"])
        category = category_map.get(pair)
        if category is None:
            raise RuntimeError(f"Classification category unavailable: {pair}")
        obj = ServiceClassification.objects.create(
            service=service,
            category=category,
            source_import_row=rows_by_id.get(item.get("source_import_row_id")),
        )
        _record_change(
            batch=batch,
            action="CLASSIFICATION_ADD",
            obj=obj,
            import_row=obj.source_import_row,
            service=service,
        )

    for item in plan["core"]["commercial"]:
        service = service_map[item["service_identity"]]
        obj = ServiceCommercial.objects.create(
            service=service,
            label=item["label"],
            minimum_charge_raw=item["minimum_charge_raw"],
            minimum_charge=item["minimum_charge"],
            government_fee_raw=item["government_fee_raw"],
            government_fee=item["government_fee"],
            vendor_cost_raw=item["vendor_cost_raw"],
            vendor_cost=item["vendor_cost"],
            bdm_deduction_raw=item["bdm_deduction_raw"],
            bdm_deduction=item["bdm_deduction"],
            remarks=item["remarks"],
            visibility="ADMIN_ONLY",
            source_import_row=rows_by_id.get(item.get("source_import_row_id")),
            is_active=item.get("is_active", True),
        )
        _record_change(
            batch=batch,
            action="COMMERCIAL_CREATE",
            obj=obj,
            import_row=obj.source_import_row,
            service=service,
        )

    for item in plan["sources"]["plans"]:
        service = service_map[item["service_identity"]]
        obj = ServiceSource.objects.create(
            service=service,
            source_name=item["source_name"],
            source_url=item["source_url"],
            source_kind=item["source_kind"],
            import_row=rows_by_id.get(item.get("import_row_id")),
            source_reference=item["source_reference"],
            is_official=item["is_official"],
            notes=item["notes"],
        )
        _record_change(
            batch=batch,
            action="SOURCE_ADD",
            obj=obj,
            import_row=obj.import_row,
            service=service,
        )

    for item in plan["references"]:
        obj = ReferenceItem.objects.create(
            dataset_name=item["dataset_name"],
            key=item["key"],
            value=item["value"],
            metadata=item["metadata"],
            visibility="ADMIN_ONLY",
            source_import_row=rows_by_id.get(item.get("source_import_row_id")),
        )
        _record_change(
            batch=batch,
            action="REFERENCE_CREATE",
            obj=obj,
            import_row=obj.source_import_row,
        )

    matrix_plan = plan["comparison"]["matrix"]
    matrix = ComparisonMatrix.objects.create(
        name=matrix_plan["name"],
        source_sheet=matrix_plan["source_sheet"],
        import_batch=batch,
        metadata=matrix_plan["metadata"],
    )
    _record_change(batch=batch, action="OTHER", obj=matrix)

    for item in plan["comparison"]["entries"]:
        linked_service = (
            service_map.get(item.get("service_identity"))
            if item.get("service_identity")
            else None
        )
        obj = ComparisonEntry.objects.create(
            matrix=matrix,
            row_number=item["row_number"],
            column_name=item["column_name"],
            row_label=item["row_label"],
            value_raw=item["value_raw"],
            service=linked_service,
            source_import_row=rows_by_id.get(item.get("source_import_row_id")),
        )
        _record_change(
            batch=batch,
            action="OTHER",
            obj=obj,
            import_row=obj.source_import_row,
            service=linked_service,
        )

    document_map = {}
    for item in plan["knowledge"]["documents"]:
        obj = KnowledgeDocument.objects.create(
            document_key=item["document_key"],
            title=item["title"],
            source_sheet=item["source_sheet"],
            source_import_batch=batch,
            status="DRAFT",
            visibility="ADMIN_ONLY",
            metadata=item["metadata"],
        )
        document_map[item["document_key"]] = obj
        _record_change(batch=batch, action="OTHER", obj=obj)

    for item in plan["knowledge"]["sections"]:
        linked_service = (
            service_map.get(item["linked_service_identity"])
            if item.get("linked_service_identity")
            else None
        )
        obj = KnowledgeSection.objects.create(
            document=document_map[item["document_key"]],
            linked_service=linked_service,
            section_type=item["section_type"],
            title=item["title"],
            content=item["content"],
            display_order=item["display_order"],
            is_heading=item["is_heading"],
            visibility="ADMIN_ONLY",
            source_import_row=rows_by_id[item["source_import_row_id"]],
        )
        _record_change(
            batch=batch,
            action="CONTENT_CREATE",
            obj=obj,
            import_row=obj.source_import_row,
            service=linked_service,
        )

    comm = plan["communication"]
    template = CommunicationTemplate.objects.create(
        template_key=comm["template_key"],
        title=comm["title"],
        subject=comm["subject"],
        body=comm["body"],
        status="DRAFT",
        visibility="ADMIN_ONLY",
        source_import_batch=batch,
        source_sheet=comm["source_sheet"],
    )
    _record_change(batch=batch, action="OTHER", obj=template)

    service_for_row = {}
    merge_row_ids = set()
    for identity, item in plan["core"]["services"].items():
        service = service_map[identity]
        for row_id in item["source_row_ids"]:
            service_for_row[row_id] = service
        merge_row_ids.update(item.get("rolling_merge_row_ids", []))

    now = timezone.now()
    for row in staged_rows:
        row.import_outcomes = plan["row_outcomes"][row.id]
        row.processed_at = now
        row.imported_service = service_for_row.get(row.id)
        row.matched_service = service_for_row.get(row.id) if row.id in merge_row_ids else None
        row.save(
            update_fields=[
                "import_outcomes",
                "processed_at",
                "imported_service",
                "matched_service",
            ]
        )

    batch.status = "IMPORTED"
    batch.imported_at = now
    metadata = deepcopy(batch.metadata or {})
    metadata["final_import"] = {
        "contract_version": 4,
        "services": len(service_map),
        "categories_created": len(created_categories),
        "knowledge_documents": len(document_map),
        "knowledge_sections": len(plan["knowledge"]["sections"]),
        "row_outcomes": len(plan["row_outcomes"]),
        "rolling_lineage": plan["rolling_lineage_audit"],
        "business_field_audit": plan["business_field_audit"],
        "preserve_only_by_sheet": plan["preserve_only_by_sheet"],
    }
    batch.metadata = metadata
    batch.save(update_fields=["status", "imported_at", "metadata"])

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "services_created": len(service_map),
        "categories_created": len(created_categories),
        "knowledge_documents": len(document_map),
        "knowledge_sections": len(plan["knowledge"]["sections"]),
        "row_outcomes": len(plan["row_outcomes"]),
        "ledger_rows": ImportChange.objects.filter(import_batch=batch).count(),
    }


def preflight():
    baseline = assert_preimport_baseline()
    integrity = database_integrity()
    plan = build_final_import_plan()
    if plan["rolling_lineage_audit"] != {"covered": 7, "merged": 5, "new": 2}:
        raise RuntimeError("Rolling lineage preflight failed.")
    if len(plan["row_outcomes"]) != 478:
        raise RuntimeError("478-row reconciliation failed.")
    return {
        "database": integrity,
        "baseline": baseline,
        "plan": {
            "services": len(plan["core"]["services"]),
            "categories": len(plan["core"]["categories"]),
            "classifications": len(plan["core"]["classifications"]),
            "commercial": len(plan["core"]["commercial"]),
            "sources": len(plan["sources"]["plans"]),
            "references": len(plan["references"]),
            "comparison_entries": len(plan["comparison"]["entries"]),
            "knowledge_documents": len(plan["knowledge"]["documents"]),
            "knowledge_sections": len(plan["knowledge"]["sections"]),
            "communication_templates": 1,
            "row_outcomes": len(plan["row_outcomes"]),
            "rolling_lineage": plan["rolling_lineage_audit"],
            "business_field_audit": plan["business_field_audit"],
            "preserve_only_by_sheet": plan["preserve_only_by_sheet"],
        },
    }


def rehearse_import():
    before = baseline_counts()
    assert_preimport_baseline()
    plan = build_final_import_plan()
    with transaction.atomic():
        _execute(plan)
        transaction.set_rollback(True)
    after = baseline_counts()
    if after != before:
        raise RuntimeError(f"Forced rollback changed counts. Before={before}; After={after}")
    batch = ImportBatch.objects.get(pk=5)
    if batch.status != "PREVIEWED":
        raise RuntimeError("Forced rollback changed Batch #5 status.")
    dirty_rows = ImportRow.objects.filter(import_batch=batch, processed_at__isnull=False).count()
    if dirty_rows:
        raise RuntimeError("Forced rollback left processed ImportRows.")
    return {
        "rehearsal": "PASS",
        "counts_unchanged": True,
        "batch_status": batch.status,
        "processed_rows_after_rollback": dirty_rows,
    }


def run_import():
    assert_preimport_baseline()
    database_integrity()
    plan = build_final_import_plan()
    with transaction.atomic():
        result = _execute(plan)
    database_integrity()
    return result


def rollback_import(rolled_back_by=None):
    batch = ImportBatch.objects.get(pk=5)
    if batch.status != "IMPORTED":
        raise RuntimeError(f"Batch #5 must be IMPORTED; current={batch.status}")
    changes = list(
        ImportChange.objects.filter(import_batch=batch, is_reversed=False).order_by("-id")
    )
    if not changes:
        raise RuntimeError("No unreversed ImportChange ledger rows exist.")
    now = timezone.now()
    with transaction.atomic():
        for change in changes:
            if change.object_model and change.object_pk:
                try:
                    app_label, model_name = change.object_model.split(".", 1)
                    model = apps.get_model(app_label, model_name)
                except Exception as exc:
                    raise RuntimeError(
                        f"Rollback cannot resolve model {change.object_model!r}."
                    ) from exc
                obj = model.objects.filter(pk=change.object_pk).first()
                if obj is not None:
                    obj.delete()
            change.is_reversed = True
            change.reversed_at = now
            change.save(update_fields=["is_reversed", "reversed_at"])

        for row in ImportRow.objects.filter(import_batch=batch):
            row.imported_service = None
            row.matched_service = None
            row.processed_at = None
            row.import_outcomes = []
            row.save(
                update_fields=[
                    "imported_service",
                    "matched_service",
                    "processed_at",
                    "import_outcomes",
                ]
            )

        batch.status = "ROLLED_BACK"
        batch.rolled_back_at = now
        batch.rolled_back_by = rolled_back_by
        batch.save(update_fields=["status", "rolled_back_at", "rolled_back_by"])
    database_integrity()
    return {
        "rollback": "PASS",
        "batch_status": batch.status,
        "ledger_rows_reversed": len(changes),
    }
'''

(IMPORTING / "execution.py").write_text(execution, encoding="utf-8")

# ---------------------------------------------------------------------------
# management command
# ---------------------------------------------------------------------------
COMMANDS.mkdir(parents=True, exist_ok=True)
(MANAGEMENT / "__init__.py").touch()
(COMMANDS / "__init__.py").touch()

command = r'''from django.core.management.base import BaseCommand, CommandError

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
'''

(COMMANDS / "toolkit_final_import.py").write_text(command, encoding="utf-8")

# ---------------------------------------------------------------------------
# Static verification + migration generation (not apply)
# ---------------------------------------------------------------------------
changed_files = [
    MODELS,
    IMPORTING / "final_plan.py",
    IMPORTING / "execution.py",
    COMMANDS / "toolkit_final_import.py",
]

print("\n===== COMPILE =====")
for path in changed_files:
    subprocess.run([sys.executable, "-m", "py_compile", str(path)], check=True)
print("PASS")

print("\n===== DJANGO CHECK =====")
subprocess.run([sys.executable, "manage.py", "check"], check=True)

print("\n===== GENERATE MIGRATION (NOT APPLY) =====")
subprocess.run(
    [
        sys.executable,
        "manage.py",
        "makemigrations",
        "toolkit",
        "--name",
        "final_import_knowledge_architecture",
    ],
    check=True,
)

print("\n===== MIGRATION STATIC INSPECTION =====")
migration_matches = sorted(
    (ROOT / "toolkit" / "migrations").glob(
        "*_final_import_knowledge_architecture.py"
    )
)
if len(migration_matches) != 1:
    raise SystemExit(
        "STOP: expected exactly one generated final-import migration; "
        f"found {len(migration_matches)}"
    )
migration_path = migration_matches[0]
migration_text = migration_path.read_text(encoding="utf-8")
for forbidden in (
    "migrations.DeleteModel(",
    "migrations.RemoveField(",
    "migrations.AlterField(",
    "migrations.RenameField(",
    "migrations.RenameModel(",
    "migrations.RunPython(",
    "migrations.RunSQL(",
):
    if forbidden in migration_text:
        raise SystemExit(
            f"STOP: generated migration contains forbidden operation: {forbidden}"
        )
for required in (
    "name='KnowledgeDocument'",
    "name='KnowledgeSection'",
    "name='import_outcomes'",
    "name='object_model'",
    "name='object_pk'",
):
    if required not in migration_text:
        raise SystemExit(
            f"STOP: generated migration is missing expected operation marker: {required}"
        )
print(f"PASS: {migration_path.name}")

print("\n===== FINAL STATIC CHECK =====")
subprocess.run([sys.executable, "manage.py", "check"], check=True)

print("\n============================================================")
print("PATCH COMPLETE")
print("DATABASE MIGRATION APPLIED: NO")
print("LIVE IMPORT STARTED: NO")
print(f"BACKUP DIRECTORY: {backup_dir}")
print(f"CONTRACT V4 SHA256: {contract_hash}")
print("============================================================")
