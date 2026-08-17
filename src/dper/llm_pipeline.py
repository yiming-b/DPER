from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dataset import build_dataset_csv
from .dictionary import compact_dictionary_rows, load_dictionary, select_dictionary_subset
from .pdf_text import ExtractedReport, chunk_pages, extract_pdf_text, read_reports
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .providers import LLMProvider
from .schema import (
    CANDIDATE_COLUMNS,
    DIAG_COLUMNS,
    DOG_SUMMARY_COLUMNS,
    EVENT_COLUMNS,
    LAB_COLUMNS,
    MED_COLUMNS,
    PROC_COLUMNS,
    SCHEMA_VERSION,
    STATUS_VALUES,
    TABLE_COLUMNS,
    VISIT_COLUMNS,
)
from .utils import coerce_str, norm_space, parse_json_object, read_json_list, redact_private_text


@dataclass
class RunConfig:
    input_path: Path
    output_dir: Path
    provider: LLMProvider
    dictionary_path: Path | None = None
    append: bool = False
    chunk_chars: int = 18000
    max_dictionary_rows: int = 120
    redact: bool = True
    dataset_identity_columns: list[str] | None = None


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.exists() else "w"
    with path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if mode == "w":
            writer.writeheader()
        for row in rows:
            writer.writerow({column: coerce_str(row.get(column, "")) for column in columns})


def _empty_rows() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in TABLE_COLUMNS}


def _merge_dog(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    for key, value in (update or {}).items():
        if value not in (None, "", [], {}) and not base.get(key):
            base[key] = value
    return base


def _clean_status(value: Any) -> str:
    status = norm_space(coerce_str(value)).lower()
    return status if status in STATUS_VALUES else "not_reported"


def _page(value: Any, default_page: int) -> str:
    value = coerce_str(value).strip()
    return value or str(default_page)


def _confidence(value: Any, default: str = "0.70") -> str:
    if value in (None, ""):
        return default
    return coerce_str(value)


def _dict_value(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return coerce_str(data[key])
    return ""


def _visit_row(
    *,
    visit: dict[str, Any],
    visit_id: str,
    dog_id: str,
    report: ExtractedReport,
    default_page: int,
) -> dict[str, Any]:
    vitals = visit.get("vitals") if isinstance(visit.get("vitals"), dict) else {}
    diet_env = visit.get("diet_environment") if isinstance(visit.get("diet_environment"), dict) else {}
    exams = visit.get("exam_summaries") if isinstance(visit.get("exam_summaries"), dict) else {}
    row = {column: "" for column in VISIT_COLUMNS}
    row.update(
        {
            "visit_id": visit_id,
            "dog_id": dog_id,
            "source_report_id": report.report.report_id,
            "source_file": str(report.report.path),
            "visit_date": _dict_value(visit, "visit_date"),
            "document_date": _dict_value(visit, "document_date"),
            "visit_type": _dict_value(visit, "visit_type"),
            "visit_reason_raw": _dict_value(visit, "visit_reason_raw"),
            "chief_complaint_normalized": _dict_value(visit, "chief_complaint_normalized"),
            "age_at_visit_years": _dict_value(visit, "age_at_visit_years"),
            "weight_lb": _dict_value(vitals, "weight_lb"),
            "weight_kg": _dict_value(vitals, "weight_kg"),
            "body_condition_score": _dict_value(vitals, "body_condition_score", "bcs"),
            "body_condition_scale": _dict_value(vitals, "body_condition_scale"),
            "muscle_condition_score": _dict_value(vitals, "muscle_condition_score"),
            "pain_score": _dict_value(vitals, "pain_score"),
            "pain_score_scale": _dict_value(vitals, "pain_score_scale"),
            "temperature_f": _dict_value(vitals, "temperature_f"),
            "heart_rate_bpm": _dict_value(vitals, "heart_rate_bpm"),
            "respiratory_rate_bpm": _dict_value(vitals, "respiratory_rate_bpm"),
            "crt_seconds": _dict_value(vitals, "crt_seconds"),
            "mucous_membrane_color": _dict_value(vitals, "mucous_membrane_color"),
            "hydration_status": _dict_value(vitals, "hydration_status"),
            "mentation_attitude": _dict_value(vitals, "mentation_attitude"),
            "current_medications_raw": _dict_value(diet_env, "current_medications_raw", "current_medications"),
            "current_diet_raw": _dict_value(diet_env, "current_diet_raw", "current_diet"),
            "environment_exposure_raw": _dict_value(diet_env, "environment_exposure_raw", "environment_exposure"),
            "general_appearance_exam": _dict_value(exams, "general_appearance_exam", "general_appearance"),
            "eyes_exam": _dict_value(exams, "eyes_exam", "eyes"),
            "ears_exam": _dict_value(exams, "ears_exam", "ears"),
            "nose_exam": _dict_value(exams, "nose_exam", "nose"),
            "oral_dental_exam": _dict_value(exams, "oral_dental_exam", "oral_dental"),
            "skin_coat_exam": _dict_value(exams, "skin_coat_exam", "skin_coat"),
            "lymph_nodes_exam": _dict_value(exams, "lymph_nodes_exam", "lymph_nodes"),
            "cardiovascular_exam": _dict_value(exams, "cardiovascular_exam", "cardiovascular"),
            "respiratory_exam": _dict_value(exams, "respiratory_exam", "respiratory"),
            "abdomen_gi_exam": _dict_value(exams, "abdomen_gi_exam", "abdomen_gi"),
            "urogenital_exam": _dict_value(exams, "urogenital_exam", "urogenital"),
            "perineal_anal_gland_exam": _dict_value(exams, "perineal_anal_gland_exam", "perineal_anal_gland"),
            "musculoskeletal_gait_exam": _dict_value(exams, "musculoskeletal_gait_exam", "musculoskeletal_gait"),
            "neurologic_exam": _dict_value(exams, "neurologic_exam", "neurologic"),
            "rectal_exam": _dict_value(exams, "rectal_exam", "rectal"),
            "evidence_quote": _dict_value(visit, "evidence_quote", "source_sentence"),
            "page_number": _page(visit.get("page_number"), default_page),
            "confidence": _confidence(visit.get("confidence"), "0.65"),
            "schema_version": SCHEMA_VERSION,
        }
    )
    return row


def _dog_summary_row(dog: dict[str, Any], dog_id: str, report: ExtractedReport) -> dict[str, Any]:
    row = {column: "" for column in DOG_SUMMARY_COLUMNS}
    row.update(
        {
            "dog_id": dog_id,
            "source_report_id": report.report.report_id,
            "source_file": str(report.report.path),
            "extraction_status": report.extraction_status,
            "dog_name": _dict_value(dog, "dog_name"),
            "species": _dict_value(dog, "species") or "canine",
            "breed_raw": _dict_value(dog, "breed_raw"),
            "breed_primary": _dict_value(dog, "breed_primary"),
            "mixed_breed_status": _dict_value(dog, "mixed_breed_status"),
            "sex_raw": _dict_value(dog, "sex_raw"),
            "sex": _dict_value(dog, "sex"),
            "reproductive_status": _dict_value(dog, "reproductive_status"),
            "date_of_birth": _dict_value(dog, "date_of_birth"),
            "age_reported": _dict_value(dog, "age_reported"),
            "age_years_at_report": _dict_value(dog, "age_years_at_report"),
            "coat_color": _dict_value(dog, "coat_color"),
            "microchip_id_present": _dict_value(dog, "microchip_id_present"),
            "rabies_tag_or_id_present": _dict_value(dog, "rabies_tag_or_id_present"),
            "source_facility": _dict_value(dog, "source_facility"),
            "evidence_quote": _dict_value(dog, "evidence_quote"),
            "schema_version": SCHEMA_VERSION,
        }
    )
    return row


def _flatten_visit_children(
    *,
    rows: dict[str, list[dict[str, Any]]],
    visit: dict[str, Any],
    visit_id: str,
    dog_id: str,
    report: ExtractedReport,
    visit_date: str,
    default_page: int,
    phenotype_ids: set[str],
) -> None:
    for item in visit.get("phenotype_events") or []:
        if not isinstance(item, dict):
            continue
        event_id = f"{report.report.report_id}_E{len(rows['phenotype_events.csv']) + 1:05d}"
        phenotype_id = _dict_value(item, "phenotype_id")
        status = _clean_status(item.get("status"))
        rows["phenotype_events.csv"].append(
            {
                "event_id": event_id,
                "dog_id": dog_id,
                "visit_id": visit_id,
                "source_report_id": report.report.report_id,
                "source_file": str(report.report.path),
                "visit_date": visit_date,
                "phenotype_id": phenotype_id,
                "status": status,
                "value_raw": _dict_value(item, "value_raw"),
                "value_normalized": _dict_value(item, "value_normalized"),
                "unit": _dict_value(item, "unit"),
                "body_site": _dict_value(item, "body_site"),
                "laterality": _dict_value(item, "laterality"),
                "severity": _dict_value(item, "severity"),
                "duration": _dict_value(item, "duration"),
                "onset_date": _dict_value(item, "onset_date"),
                "resolved_date": _dict_value(item, "resolved_date"),
                "temporality": _dict_value(item, "temporality"),
                "negation": _dict_value(item, "negation"),
                "source_sentence": _dict_value(item, "source_sentence", "evidence_quote"),
                "page_number": _page(item.get("page_number"), default_page),
                "confidence": _confidence(item.get("confidence")),
                "needs_review": "yes" if phenotype_id not in phenotype_ids or status == "not_reported" else _dict_value(item, "needs_review") or "no",
                "schema_version": SCHEMA_VERSION,
            }
        )

    for item in visit.get("lab_results") or []:
        if not isinstance(item, dict):
            continue
        rows["lab_results.csv"].append(
            {
                "lab_result_id": f"{report.report.report_id}_L{len(rows['lab_results.csv']) + 1:05d}",
                "dog_id": dog_id,
                "visit_id": visit_id,
                "source_report_id": report.report.report_id,
                "source_file": str(report.report.path),
                "collection_date": _dict_value(item, "collection_date") or visit_date,
                "source_panel": _dict_value(item, "source_panel"),
                "specimen": _dict_value(item, "specimen"),
                "analyte_raw": _dict_value(item, "analyte_raw"),
                "analyte_normalized": _dict_value(item, "analyte_normalized"),
                "value_raw": _dict_value(item, "value_raw", "value"),
                "value_numeric": _dict_value(item, "value_numeric"),
                "unit": _dict_value(item, "unit"),
                "reference_low": _dict_value(item, "reference_low"),
                "reference_high": _dict_value(item, "reference_high"),
                "flag": _dict_value(item, "flag"),
                "source_sentence": _dict_value(item, "source_sentence", "evidence_quote"),
                "page_number": _page(item.get("page_number"), default_page),
                "confidence": _confidence(item.get("confidence")),
                "schema_version": SCHEMA_VERSION,
            }
        )

    for item in visit.get("diagnostic_events") or []:
        if not isinstance(item, dict):
            continue
        rows["diagnostic_events.csv"].append(
            {
                "diagnostic_event_id": f"{report.report.report_id}_D{len(rows['diagnostic_events.csv']) + 1:05d}",
                "dog_id": dog_id,
                "visit_id": visit_id,
                "source_report_id": report.report.report_id,
                "source_file": str(report.report.path),
                "event_date": _dict_value(item, "event_date") or visit_date,
                "diagnostic_type": _dict_value(item, "diagnostic_type"),
                "status": _clean_status(item.get("status")),
                "body_site": _dict_value(item, "body_site"),
                "result_summary": _dict_value(item, "result_summary"),
                "source_sentence": _dict_value(item, "source_sentence", "evidence_quote"),
                "page_number": _page(item.get("page_number"), default_page),
                "confidence": _confidence(item.get("confidence")),
                "schema_version": SCHEMA_VERSION,
            }
        )

    for item in visit.get("medication_events") or []:
        if not isinstance(item, dict):
            continue
        rows["medication_events.csv"].append(
            {
                "medication_event_id": f"{report.report.report_id}_M{len(rows['medication_events.csv']) + 1:05d}",
                "dog_id": dog_id,
                "visit_id": visit_id,
                "source_report_id": report.report.report_id,
                "source_file": str(report.report.path),
                "event_date": _dict_value(item, "event_date") or visit_date,
                "medication_name_raw": _dict_value(item, "medication_name_raw", "medication_name"),
                "medication_class": _dict_value(item, "medication_class"),
                "status": _clean_status(item.get("status")),
                "dose_raw": _dict_value(item, "dose_raw", "dose"),
                "route_raw": _dict_value(item, "route_raw", "route"),
                "frequency_raw": _dict_value(item, "frequency_raw", "frequency"),
                "source_sentence": _dict_value(item, "source_sentence", "evidence_quote"),
                "page_number": _page(item.get("page_number"), default_page),
                "confidence": _confidence(item.get("confidence")),
                "schema_version": SCHEMA_VERSION,
            }
        )

    for item in visit.get("procedure_events") or []:
        if not isinstance(item, dict):
            continue
        rows["procedure_events.csv"].append(
            {
                "procedure_event_id": f"{report.report.report_id}_P{len(rows['procedure_events.csv']) + 1:05d}",
                "dog_id": dog_id,
                "visit_id": visit_id,
                "source_report_id": report.report.report_id,
                "source_file": str(report.report.path),
                "event_date": _dict_value(item, "event_date") or visit_date,
                "procedure_type": _dict_value(item, "procedure_type"),
                "status": _clean_status(item.get("status")),
                "body_site": _dict_value(item, "body_site"),
                "source_sentence": _dict_value(item, "source_sentence", "evidence_quote"),
                "page_number": _page(item.get("page_number"), default_page),
                "confidence": _confidence(item.get("confidence")),
                "schema_version": SCHEMA_VERSION,
            }
        )


def _append_candidates(
    rows: dict[str, list[dict[str, Any]]],
    data: dict[str, Any],
    dog_id: str,
    report: ExtractedReport,
) -> None:
    for item in data.get("new_candidate_phenotypes") or []:
        if not isinstance(item, dict):
            continue
        rows["new_candidate_phenotypes.csv"].append(
            {
                "candidate_id": f"{report.report.report_id}_C{len(rows['new_candidate_phenotypes.csv']) + 1:05d}",
                "dog_id": dog_id,
                "source_report_id": report.report.report_id,
                "source_file": str(report.report.path),
                "candidate_name": _dict_value(item, "candidate_name", "name", "phenotype"),
                "suggested_category": _dict_value(item, "suggested_category", "category"),
                "evidence_quote": _dict_value(item, "evidence_quote", "source_sentence"),
                "page_number": _page(item.get("page_number"), 1),
                "rationale": _dict_value(item, "rationale", "notes"),
                "schema_version": SCHEMA_VERSION,
            }
        )


def _process_report(
    report: ExtractedReport,
    *,
    provider: LLMProvider,
    dictionary_rows: list[dict[str, str]],
    max_dictionary_rows: int,
    chunk_chars: int,
    redact: bool,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    rows = _empty_rows()
    phenotype_ids = {row.get("phenotype_id", "") for row in dictionary_rows}
    merged_dog: dict[str, Any] = {}
    llm_errors: list[str] = []
    dog_id = report.report.report_id.lower()

    chunks = chunk_pages(report.pages, chunk_chars)
    for chunk_number, (page_start, page_end, chunk_text) in enumerate(chunks, 1):
        source_text = redact_private_text(chunk_text) if redact else chunk_text
        subset = compact_dictionary_rows(select_dictionary_subset(dictionary_rows, source_text, max_dictionary_rows))
        user_prompt = build_user_prompt(
            schema_version=SCHEMA_VERSION,
            source_file=str(report.report.path.name),
            report_id=report.report.report_id,
            chunk_id=f"{report.report.report_id}_chunk_{chunk_number:04d}",
            page_start=page_start,
            page_end=page_end,
            dictionary_subset=subset,
            chunk_text=source_text,
        )
        try:
            raw = provider.generate(SYSTEM_PROMPT, user_prompt)
            data = parse_json_object(raw)
        except Exception as exc:
            llm_errors.append(f"chunk {chunk_number}: {exc.__class__.__name__}: {exc}")
            continue

        if isinstance(data.get("dog"), dict):
            _merge_dog(merged_dog, data["dog"])

        visits = data.get("visits") if isinstance(data.get("visits"), list) else []
        for visit in visits:
            if not isinstance(visit, dict):
                continue
            visit_id = f"{report.report.report_id}_V{len(rows['visit_summary.csv']) + 1:05d}"
            visit_row = _visit_row(visit=visit, visit_id=visit_id, dog_id=dog_id, report=report, default_page=page_start)
            rows["visit_summary.csv"].append(visit_row)
            _flatten_visit_children(
                rows=rows,
                visit=visit,
                visit_id=visit_id,
                dog_id=dog_id,
                report=report,
                visit_date=visit_row["visit_date"],
                default_page=page_start,
                phenotype_ids=phenotype_ids,
            )
        _append_candidates(rows, data, dog_id, report)

    dog_name = _dict_value(merged_dog, "dog_name") or report.report.path.stem
    if not rows["visit_summary.csv"]:
        rows["visit_summary.csv"].append(
            _visit_row(visit={"visit_type": "unknown", "evidence_quote": "No visit extracted."}, visit_id=f"{report.report.report_id}_V00001", dog_id=dog_id, report=report, default_page=1)
        )
    rows["dog_summary.csv"].append(_dog_summary_row(merged_dog, dog_id, report))

    manifest = {
        "report_id": report.report.report_id,
        "source_file": str(report.report.path),
        "sha256": report.report.sha256,
        "duplicate_count": report.report.duplicate_count,
        "extraction_status": report.extraction_status,
        "text_chars": report.text_chars,
        "chunks": len(chunks),
        "llm_provider": provider.__class__.__name__,
        "llm_model": provider.model,
        "llm_errors": llm_errors,
        "dog_id": dog_id,
        "dog_name": dog_name,
    }
    return rows, manifest


def run_extraction(config: RunConfig) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    dictionary_rows = load_dictionary(config.dictionary_path)
    reports = read_reports(config.input_path)
    total_candidate_reports = len(reports)

    existing_manifest = read_json_list(config.output_dir / "run_manifest.json") if config.append else []
    seen_hashes = {coerce_str(row.get("sha256")) for row in existing_manifest if row.get("sha256")}
    if config.append:
        reports = [report for report in reports if report.sha256 not in seen_hashes]

    all_rows = _empty_rows()
    run_manifest: list[dict[str, Any]] = []
    for report_input in reports:
        extracted = extract_pdf_text(report_input)
        rows, manifest = _process_report(
            extracted,
            provider=config.provider,
            dictionary_rows=dictionary_rows,
            max_dictionary_rows=config.max_dictionary_rows,
            chunk_chars=config.chunk_chars,
            redact=config.redact,
        )
        for table_name, table_rows in rows.items():
            all_rows[table_name].extend(table_rows)
        run_manifest.append(manifest)

    for table_name, columns in TABLE_COLUMNS.items():
        write_csv(config.output_dir / table_name, all_rows[table_name], columns, append=config.append)

    dataset_path = build_dataset_csv(config.output_dir, config.dictionary_path, config.dataset_identity_columns)
    combined_manifest = existing_manifest + run_manifest
    (config.output_dir / "run_manifest.json").write_text(json.dumps(combined_manifest, indent=2), encoding="utf-8")

    summary = {
        "reports_processed": len(reports),
        "reports_skipped_existing": total_candidate_reports - len(reports) if config.append else 0,
        "output_dir": str(config.output_dir),
        "tables": {name: len(rows) for name, rows in all_rows.items()},
        "provider": config.provider.__class__.__name__,
        "model": config.provider.model,
        "dataset_csv": str(dataset_path),
    }
    (config.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
