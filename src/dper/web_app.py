from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from flask import Flask, abort, render_template, request, send_file

from .dataset import preview_csv
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


def repo_root() -> Path:
    return Path.cwd()


def local_models() -> list[Path]:
    models_dir = repo_root() / "models"
    if not models_dir.exists():
        return []
    return sorted(models_dir.glob("*.gguf"))


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
                "detail": f"Recommended local semantic model. Not downloaded yet. Run python .\\scripts\\setup_local_qwen.py.",
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

        try:
            provider = make_provider(provider_name, api_key=api_key, model=model, local_model=local_model)
            summary = run_extraction(
                RunConfig(
                    input_path=upload_dir,
                    output_dir=output_dir,
                    provider=provider,
                    append=False,
                    chunk_chars=int(request.form.get("chunk_chars") or 18000),
                    max_dictionary_rows=int(request.form.get("max_dictionary_rows") or 120),
                    redact=request.form.get("redact", "on") == "on",
                )
            )
        except (ProviderError, ValueError, RuntimeError) as exc:
            return _render_error(str(exc))

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
            )
        )

    def _render_error(message: str):
        return (
            render_template(
                "index.html",
                **template_context(
                    summary=None,
                    error=message,
                    dataset_preview=None,
                    dataset_download_url=None,
                    zip_download_url=None,
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
