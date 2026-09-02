"""BharatNXT Wave final production import planner (no DB writes)."""

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
