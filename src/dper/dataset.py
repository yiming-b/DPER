from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .dictionary import is_extractable_phenotype_row, load_dictionary

STATUS_PRIORITY = {
    "present": 90,
    "abnormal": 85,
    "suspected": 80,
    "rule_out": 70,
    "historical": 60,
    "resolved": 50,
    "absent": 40,
    "normal": 30,
    "not_reported": 0,
    "": 0,
}

BASE_COLUMNS = [
    "dog_id",
    "source_report_id",
    "source_file",
    "extraction_status",
    "dog_name",
    "species",
    "breed_raw",
    "breed_primary",
    "mixed_breed_status",
    "sex_raw",
    "sex",
    "reproductive_status",
    "date_of_birth",
    "coat_color",
    "phenotype_event_count",
    "new_candidate_phenotype_count",
]

WEB_IDENTITY_COLUMNS = [
    "dog_id",
    "source_file",
    "dog_name",
    "species",
    "breed_raw",
    "sex",
    "reproductive_status",
    "date_of_birth",
    "coat_color",
    "weight_lb",
    "weight_kg",
    "visit_dates",
]

WEB_META_COLUMNS = [
    "phenotype_event_count",
    "new_candidate_phenotype_count",
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_csv_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _best_status(current: str, candidate: str) -> str:
    return candidate if STATUS_PRIORITY.get(candidate, 0) > STATUS_PRIORITY.get(current, 0) else current


def _unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _format_list(values: list[str]) -> str:
    values = _unique_in_order([value for value in values if value])
    if not values:
        return ""
    return values[0] if len(values) == 1 else "|".join(values)


def _visit_rollups(visit_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    by_dog: dict[str, dict[str, list[str]]] = {}
    for visit in visit_rows:
        dog_id = visit.get("dog_id", "")
        if not dog_id:
            continue
        if dog_id not in by_dog:
            by_dog[dog_id] = {"visit_dates": [], "weight_lb": [], "weight_kg": []}
        by_dog[dog_id]["visit_dates"].append(visit.get("visit_date", ""))
        by_dog[dog_id]["weight_lb"].append(visit.get("weight_lb", ""))
        by_dog[dog_id]["weight_kg"].append(visit.get("weight_kg", ""))

    return {
        dog_id: {column: _format_list(values) for column, values in grouped.items()}
        for dog_id, grouped in by_dog.items()
    }


def _dictionary_phenotype_ids(dictionary_rows: list[dict[str, str]]) -> list[str]:
    return _unique_in_order(
        [
            row.get("phenotype_id", "")
            for row in dictionary_rows
            if is_extractable_phenotype_row(row)
        ]
    )


def build_dataset_csv(output_dir: Path, dictionary_path: Path | None = None, identity_columns: list[str] | None = None) -> Path:
    dog_rows = read_csv_rows(output_dir / "dog_summary.csv")
    visit_rows = read_csv_rows(output_dir / "visit_summary.csv")
    event_rows = read_csv_rows(output_dir / "phenotype_events.csv")
    candidate_rows = read_csv_rows(output_dir / "new_candidate_phenotypes.csv")
    dictionary_rows = load_dictionary(dictionary_path)
    visit_rollups = _visit_rollups(visit_rows)

    requested_ids = _dictionary_phenotype_ids(dictionary_rows)
    event_ids = _unique_in_order([row.get("phenotype_id", "") for row in event_rows if row.get("phenotype_id")])
    observed_ids = requested_ids + [phenotype_id for phenotype_id in event_ids if phenotype_id not in requested_ids]
    columns_before_phenotypes = BASE_COLUMNS if identity_columns is None else _unique_in_order(identity_columns + WEB_META_COLUMNS)

    by_dog: dict[str, dict[str, Any]] = {}
    for dog in dog_rows:
        rollups = visit_rollups.get(dog.get("dog_id", ""), {})
        row = {column: dog.get(column, rollups.get(column, "")) for column in columns_before_phenotypes}
        row["phenotype_event_count"] = "0"
        row["new_candidate_phenotype_count"] = "0"
        for phenotype_id in observed_ids:
            row[phenotype_id] = ""
        by_dog[dog.get("dog_id", "")] = row

    counts: dict[str, int] = {}
    for event in event_rows:
        dog_id = event.get("dog_id", "")
        phenotype_id = event.get("phenotype_id", "")
        if dog_id not in by_dog or not phenotype_id:
            continue
        status = event.get("status", "")
        if status in {"absent", "normal"}:
            continue
        counts[dog_id] = counts.get(dog_id, 0) + 1
        by_dog[dog_id][phenotype_id] = _best_status(by_dog[dog_id].get(phenotype_id, ""), status)

    candidate_counts: dict[str, int] = {}
    for candidate in candidate_rows:
        dog_id = candidate.get("dog_id", "")
        candidate_counts[dog_id] = candidate_counts.get(dog_id, 0) + 1

    for dog_id, row in by_dog.items():
        row["phenotype_event_count"] = str(counts.get(dog_id, 0))
        row["new_candidate_phenotype_count"] = str(candidate_counts.get(dog_id, 0))

    columns = columns_before_phenotypes + observed_ids
    dataset_path = output_dir / "dataset.csv"
    write_csv_rows(dataset_path, list(by_dog.values()), columns)
    return dataset_path


def preview_csv(path: Path, max_rows: int = 10, max_columns: int = 18) -> dict[str, Any]:
    rows = read_csv_rows(path)
    if not rows:
        return {"columns": [], "rows": [], "total_rows": 0, "total_columns": 0}
    columns = list(rows[0].keys())
    visible_columns = columns[:max_columns]
    return {
        "columns": visible_columns,
        "rows": [{column: row.get(column, "") for column in visible_columns} for row in rows[:max_rows]],
        "total_rows": len(rows),
        "total_columns": len(columns),
    }
