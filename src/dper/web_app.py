from __future__ import annotations

import os
import csv
import re
import shutil
import uuid
from pathlib import Path

from flask import Flask, abort, render_template, request, send_file

from .dataset import WEB_IDENTITY_COLUMNS, preview_csv
from .dictionary import is_extractable_phenotype_row, load_dictionary
from .llm_pipeline import RunConfig, run_extraction
from .local_models import QWEN3_4B_MODEL_ID, default_qwen_model_path
from .providers import ProviderError, make_provider

OPENAI_MODEL_OPTIONS = [
    {"id": "gpt-5.6-luna", "label": "GPT-5.6 Luna - lower cost"},
    {"id": "gpt-5.6-terra", "label": "GPT-5.6 Terra - balanced"},
    {"id": "gpt-5.6-sol", "label": "GPT-5.6 Sol - highest quality"},
]

CLAUDE_MODEL_OPTIONS = [
    {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5 - fast"},
    {"id": "claude-sonnet-5", "label": "Claude Sonnet 5 - balanced"},
    {"id": "claude-opus-5", "label": "Claude Opus 5 - highest quality"},
]

IDENTITY_FIELD_LABELS = {
    "dog_id": "dog_id",
    "source_file": "source_file",
    "dog_name": "dog_name",
    "species": "species",
    "breed_raw": "breed",
    "sex": "sex",
    "reproductive_status": "reproductive_status",
    "date_of_birth": "date_of_birth",
    "coat_color": "color",
    "weight_lb": "weight_lb",
    "weight_kg": "weight_kg",
    "visit_dates": "visit_dates",
}

DICTIONARY_FIELDNAMES = [
    "phenotype_id",
    "target_table",
    "category",
    "field_or_phenotype",
    "data_type",
    "allowed_values_or_format",
    "unit",
    "description",
    "examples_observed_in_reports",
    "extraction_notes",
]


def repo_root() -> Path:
    return Path.cwd()


def local_models() -> list[Path]:
    models_dir = repo_root() / "models"
    if not models_dir.exists():
        return []
    return sorted(models_dir.glob("*.gguf"))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def parse_custom_phenotypes(text: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    entries: list[dict[str, str]] = []
    for raw in re.split(r"[\n,]+", text):
        label = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw).strip()
        label = re.sub(r"\s+", " ", label)
        phenotype_id = slug(label)
        if not label or not phenotype_id or phenotype_id in seen:
            continue
        seen.add(phenotype_id)
        entries.append({"id": phenotype_id, "label": label})
    return entries


def default_phenotype_rows() -> list[dict[str, str]]:
    rows = []
    seen: set[str] = set()
    for row in load_dictionary():
        if not is_extractable_phenotype_row(row):
            continue
        phenotype_id = row.get("phenotype_id", "")
        if phenotype_id in seen:
            continue
        seen.add(phenotype_id)
        rows.append(row)
    return rows


def identity_options(selected: list[str] | None = None) -> list[dict[str, object]]:
    selected_set = set(WEB_IDENTITY_COLUMNS if selected is None else selected)
    return [
        {
            "id": column,
            "label": IDENTITY_FIELD_LABELS.get(column, column),
            "selected": column in selected_set,
        }
        for column in WEB_IDENTITY_COLUMNS
    ]


def phenotype_options(selected: list[str] | None = None, custom_ids: set[str] | None = None) -> list[dict[str, object]]:
    default_rows = default_phenotype_rows()
    selected_set = {row.get("phenotype_id", "") for row in default_rows} if selected is None else set(selected)
    custom_ids = custom_ids or set()
    return [
        {
            "id": row.get("phenotype_id", ""),
            "label": row.get("field_or_phenotype", row.get("phenotype_id", "")),
            "category": row.get("category", ""),
            "selected": row.get("phenotype_id", "") in selected_set and row.get("phenotype_id", "") not in custom_ids,
            "duplicate": row.get("phenotype_id", "") in custom_ids,
        }
        for row in default_rows
    ]


def selected_identity_columns_from_form() -> list[str]:
    selected = request.form.getlist("identity_fields")
    allowed = set(WEB_IDENTITY_COLUMNS)
    return [column for column in WEB_IDENTITY_COLUMNS if column in allowed and column in selected]


def selected_default_phenotype_ids_from_form(custom_ids: set[str]) -> list[str]:
    selected = set(request.form.getlist("default_phenotypes"))
    available = [row.get("phenotype_id", "") for row in default_phenotype_rows()]
    return [phenotype_id for phenotype_id in available if phenotype_id in selected and phenotype_id not in custom_ids]


def custom_phenotype_text_from_request() -> str:
    text = request.form.get("custom_phenotypes", "")
    uploaded = request.files.get("custom_phenotype_file")
    if uploaded and uploaded.filename:
        try:
            file_text = uploaded.stream.read().decode("utf-8-sig", errors="replace")
        except Exception:
            file_text = ""
        text = "\n".join(part for part in [text, file_text] if part.strip())
    return text


def write_selected_dictionary(
    *,
    target: Path,
    selected_default_ids: list[str],
    custom_phenotypes: list[dict[str, str]],
) -> None:
    source_rows = load_dictionary()
    default_rows_by_id = {
        row.get("phenotype_id", ""): row
        for row in source_rows
        if is_extractable_phenotype_row(row)
    }
    rows = [row for row in source_rows if not is_extractable_phenotype_row(row)]
    custom_ids = {item["id"] for item in custom_phenotypes}
    for item in custom_phenotypes:
        rows.append(
            {
                "phenotype_id": item["id"],
                "target_table": "phenotype_events",
                "category": "custom",
                "field_or_phenotype": item["label"],
                "data_type": "event",
                "allowed_values_or_format": "present|suspected|rule_out|historical|resolved|abnormal|not_reported",
                "unit": "",
                "description": f"User-provided phenotype: {item['label']}",
                "examples_observed_in_reports": item["label"],
                "extraction_notes": "Added from local web UI for this run.",
            }
        )
    for phenotype_id in selected_default_ids:
        if phenotype_id in custom_ids:
            continue
        row = default_rows_by_id.get(phenotype_id)
        if row:
            rows.append(row)

    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(source_rows[0].keys()) if source_rows else DICTIONARY_FIELDNAMES
    with target.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def form_state(
    *,
    selected_identity_columns: list[str] | None = None,
    selected_default_phenotype_ids: list[str] | None = None,
    custom_phenotype_text: str = "",
) -> dict[str, object]:
    custom_phenotypes = parse_custom_phenotypes(custom_phenotype_text)
    custom_ids = {item["id"] for item in custom_phenotypes}
    default_options = phenotype_options(selected_default_phenotype_ids, custom_ids)
    active_default_count = sum(1 for option in default_options if option["selected"])
    duplicate_count = sum(1 for option in default_options if option["duplicate"])
    return {
        "identity_options": identity_options(selected_identity_columns),
        "phenotype_options": default_options,
        "custom_phenotype_text": custom_phenotype_text,
        "custom_phenotypes": custom_phenotypes,
        "custom_phenotype_count": len(custom_phenotypes),
        "active_default_phenotype_count": active_default_count,
        "duplicate_default_phenotype_count": duplicate_count,
        "final_phenotype_count": len(custom_phenotypes) + active_default_count,
    }


def default_model_options() -> list[dict[str, str]]:
    recommended = default_qwen_model_path(repo_root())
    options: list[dict[str, str]] = []
    selected_assigned = False
    if recommended.exists():
        options.append(
            {
                "id": "qwen3-4b",
                "label": "Qwen3 4B Q4_K_M",
                "detail": f"Recommended local semantic model. Downloaded: {recommended}.",
                "value": str(recommended),
                "available": "yes",
                "selected": "yes",
            }
        )
        selected_assigned = True
    else:
        options.append(
            {
                "id": "qwen3-4b",
                "label": "Qwen3 4B Q4_K_M",
                "detail": "Recommended local semantic model. Not downloaded yet. "
                "Windows: python .\\scripts\\setup_local_qwen.py. "
                "Linux/macOS: python scripts/setup_local_qwen.py. "
                "Use .venv and models inside the DPER folder.",
                "value": str(recommended),
                "available": "no",
                "selected": "no",
            }
        )
    for path in local_models():
        if path.resolve() == recommended.resolve():
            continue
        options.append(
            {
                "id": f"gguf:{path.name}",
                "label": path.name,
                "detail": f"Downloaded GGUF model: {path}",
                "value": str(path),
                "available": "yes",
                "selected": "yes" if not selected_assigned else "no",
            }
        )
        selected_assigned = True
    options.append(
        {
            "id": "builtin",
            "label": "Built-in regex/dictionary extractor",
            "detail": "Fallback extractor. Always available, fast, no API key, no model download.",
            "value": "",
            "available": "yes",
            "selected": "yes" if not selected_assigned else "no",
        }
    )
    return options


def template_context(**overrides) -> dict[str, object]:
    context = {
        "local_models": local_models(),
        "default_model_options": default_model_options(),
        "qwen_model_id": QWEN3_4B_MODEL_ID,
        "qwen_model_path": default_qwen_model_path(repo_root()),
        "qwen_model_present": default_qwen_model_path(repo_root()).exists(),
        "openai_model_options": OPENAI_MODEL_OPTIONS,
        "claude_model_options": CLAUDE_MODEL_OPTIONS,
        **form_state(),
    }
    context.update(overrides)
    return context


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent / "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            **template_context(
                summary=None,
                error=None,
                dataset_preview=None,
                dataset_download_url=None,
                zip_download_url=None,
            )
        )

    @app.post("/extract")
    def extract():
        run_id = uuid.uuid4().hex[:12]
        run_dir = repo_root() / "web_runs" / run_id
        upload_dir = run_dir / "uploads"
        output_dir = run_dir / "output"
        upload_dir.mkdir(parents=True, exist_ok=True)

        files = request.files.getlist("reports")
        pdf_paths: list[Path] = []
        for file in files:
            if not file.filename or not file.filename.lower().endswith(".pdf"):
                continue
            safe_name = Path(file.filename).name
            target = upload_dir / safe_name
            file.save(target)
            pdf_paths.append(target)

        if not pdf_paths:
            return _render_error("Upload at least one PDF report.")

        model_mode = request.form.get("model_mode", "default")
        default_model = request.form.get("default_model", "builtin")
        if model_mode == "api":
            provider_name = request.form.get("llm_provider", "openai")
        elif default_model == "builtin":
            provider_name = "default"
        elif default_model == "qwen3-4b":
            provider_name = "local-qwen"
        else:
            provider_name = "local"
        api_key = request.form.get("api_key") or None
        model = request.form.get("model") or None
        local_model = request.form.get("default_model_path") or None
        custom_phenotype_text = custom_phenotype_text_from_request()
        custom_phenotypes = parse_custom_phenotypes(custom_phenotype_text)
        custom_ids = {item["id"] for item in custom_phenotypes}
        selected_identity_columns = selected_identity_columns_from_form()
        selected_default_phenotype_ids = selected_default_phenotype_ids_from_form(custom_ids)
        if not selected_identity_columns and not selected_default_phenotype_ids and not custom_phenotypes:
            return _render_error(
                "Select identity fields, default phenotypes, or enter a custom phenotype list.",
                selected_identity_columns=selected_identity_columns,
                selected_default_phenotype_ids=selected_default_phenotype_ids,
                custom_phenotype_text=custom_phenotype_text,
            )
        selected_dictionary = run_dir / "phenotype_dictionary.selected.csv"
        write_selected_dictionary(
            target=selected_dictionary,
            selected_default_ids=selected_default_phenotype_ids,
            custom_phenotypes=custom_phenotypes,
        )

        try:
            provider = make_provider(provider_name, api_key=api_key, model=model, local_model=local_model)
            summary = run_extraction(
                RunConfig(
                    input_path=upload_dir,
                    output_dir=output_dir,
                    provider=provider,
                    dictionary_path=selected_dictionary,
                    append=False,
                    chunk_chars=int(request.form.get("chunk_chars") or 18000),
                    max_dictionary_rows=int(request.form.get("max_dictionary_rows") or 120),
                    redact=request.form.get("redact", "on") == "on",
                    dataset_identity_columns=selected_identity_columns,
                )
            )
        except (ProviderError, ValueError, RuntimeError) as exc:
            return _render_error(
                str(exc),
                selected_identity_columns=selected_identity_columns,
                selected_default_phenotype_ids=selected_default_phenotype_ids,
                custom_phenotype_text=custom_phenotype_text,
            )

        dataset_path = output_dir / "dataset.csv"
        dataset_preview = preview_csv(dataset_path)
        archive_base = run_dir / "dper_results"
        zip_path = Path(shutil.make_archive(str(archive_base), "zip", output_dir))
        return render_template(
            "index.html",
            **template_context(
                summary=summary,
                error=None,
                dataset_preview=dataset_preview,
                dataset_download_url=f"/download/{run_id}/dataset",
                zip_download_url=f"/download/{run_id}/all",
                zip_size=zip_path.stat().st_size,
                **form_state(
                    selected_identity_columns=selected_identity_columns,
                    selected_default_phenotype_ids=selected_default_phenotype_ids,
                    custom_phenotype_text=custom_phenotype_text,
                ),
            )
        )

    def _render_error(
        message: str,
        *,
        selected_identity_columns: list[str] | None = None,
        selected_default_phenotype_ids: list[str] | None = None,
        custom_phenotype_text: str = "",
    ):
        return (
            render_template(
                "index.html",
                **template_context(
                    summary=None,
                    error=message,
                    dataset_preview=None,
                    dataset_download_url=None,
                    zip_download_url=None,
                    **form_state(
                        selected_identity_columns=selected_identity_columns,
                        selected_default_phenotype_ids=selected_default_phenotype_ids,
                        custom_phenotype_text=custom_phenotype_text,
                    ),
                )
            ),
            400,
        )

    @app.get("/download/<run_id>/dataset")
    def download_dataset(run_id: str):
        if not run_id.replace("-", "").isalnum():
            abort(404)
        dataset_path = repo_root() / "web_runs" / run_id / "output" / "dataset.csv"
        if not dataset_path.exists():
            abort(404)
        return send_file(dataset_path, as_attachment=True, download_name="dataset.csv")

    @app.get("/download/<run_id>/all")
    @app.get("/download/<run_id>")
    def download_all(run_id: str):
        if not run_id.replace("-", "").isalnum():
            abort(404)
        zip_path = repo_root() / "web_runs" / run_id / "dper_results.zip"
        if not zip_path.exists():
            abort(404)
        return send_file(zip_path, as_attachment=True, download_name="dper_results.zip")

    return app


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=int(os.getenv("DPER_PORT", "7860")), debug=False)


if __name__ == "__main__":
    main()
