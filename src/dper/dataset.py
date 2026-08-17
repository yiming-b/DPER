from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .dictionary import load_dictionary

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
    "age_reported",
    "coat_color",
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


def build_dataset_csv(output_dir: Path, dictionary_path: Path | None = None) -> Path:
    dog_rows = read_csv_rows(output_dir / "dog_summary.csv")
    event_rows = read_csv_rows(output_dir / "phenotype_events.csv")
    candidate_rows = read_csv_rows(output_dir / "new_candidate_phenotypes.csv")
    dictionary_rows = load_dictionary(dictionary_path)

    observed_ids = sorted({row.get("phenotype_id", "") for row in event_rows if row.get("phenotype_id")})
    if not observed_ids:
        observed_ids = sorted(
            {
                row.get("phenotype_id", "")
                for row in dictionary_rows
                if row.get("target_table") == "phenotype_events" and row.get("phenotype_id")
            }
        )

    by_dog: dict[str, dict[str, Any]] = {}
    for dog in dog_rows:
        row = {column: dog.get(column, "") for column in BASE_COLUMNS}
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
        counts[dog_id] = counts.get(dog_id, 0) + 1
        status = event.get("status", "")
        by_dog[dog_id][phenotype_id] = _best_status(by_dog[dog_id].get(phenotype_id, ""), status)

    candidate_counts: dict[str, int] = {}
    for candidate in candidate_rows:
        dog_id = candidate.get("dog_id", "")
        candidate_counts[dog_id] = candidate_counts.get(dog_id, 0) + 1

    for dog_id, row in by_dog.items():
        row["phenotype_event_count"] = str(counts.get(dog_id, 0))
        row["new_candidate_phenotype_count"] = str(candidate_counts.get(dog_id, 0))

    columns = BASE_COLUMNS + observed_ids
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
