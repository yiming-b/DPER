from __future__ import annotations

import csv
import re
from pathlib import Path

from .utils import norm_space

COMMON_EVENT_FIELD_IDS = {
    "dog_id",
    "event_id",
    "status",
    "value_raw",
    "value_normalized",
    "body_site",
    "laterality",
    "severity",
    "duration",
    "onset_date",
    "resolved_date",
    "temporality",
    "negation",
    "source_sentence",
    "page_number",
    "confidence",
    "needs_review",
}


def default_dictionary_path() -> Path:
    cwd_path = Path.cwd() / "schemas" / "phenotype_dictionary.csv"
    if cwd_path.exists():
        return cwd_path
    return Path(__file__).resolve().parents[2] / "schemas" / "phenotype_dictionary.csv"


def load_dictionary(path: Path | None = None) -> list[dict[str, str]]:
    path = path or default_dictionary_path()
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [dict(row) for row in csv.DictReader(f)]


def is_extractable_phenotype_row(row: dict[str, str]) -> bool:
    phenotype_id = row.get("phenotype_id", "")
    return bool(
        row.get("target_table") == "phenotype_events"
        and row.get("category") != "common_event_columns"
        and phenotype_id not in COMMON_EVENT_FIELD_IDS
        and phenotype_id
        and row.get("data_type", "event") in {"", "event"}
    )


def _terms(row: dict[str, str]) -> set[str]:
    joined = " ".join(
        [
            row.get("phenotype_id", ""),
            row.get("field_or_phenotype", ""),
            row.get("description", ""),
            row.get("examples_observed_in_reports", ""),
        ]
    ).lower()
    words = {word for word in re.findall(r"[a-z][a-z0-9_/-]{2,}", joined)}
    words.update(part for part in row.get("phenotype_id", "").lower().split("_") if len(part) > 2)
    return words


def select_dictionary_subset(rows: list[dict[str, str]], chunk_text: str, max_rows: int = 120) -> list[dict[str, str]]:
    text = chunk_text.lower()
    scored: list[tuple[int, dict[str, str]]] = []
    for row in rows:
        score = 0
        phenotype_id = row.get("phenotype_id", "").lower()
        label = row.get("field_or_phenotype", "").lower()
        if phenotype_id and phenotype_id in text:
            score += 10
        if label and len(label) > 3 and label in text:
            score += 8
        score += sum(1 for term in _terms(row) if term in text)
        if is_extractable_phenotype_row(row):
            score += 1
        if score:
            scored.append((score, row))

    scored.sort(key=lambda item: (-item[0], item[1].get("phenotype_id", "")))
    selected = [row for _, row in scored[:max_rows]]
    if selected:
        return selected
    return [row for row in rows if is_extractable_phenotype_row(row)][:max_rows]


def compact_dictionary_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    keep = ["phenotype_id", "target_table", "category", "field_or_phenotype", "allowed_values_or_format", "description", "examples_observed_in_reports"]
    return [{key: norm_space(row.get(key, "")) for key in keep} for row in rows]
