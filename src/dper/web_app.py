from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from flask import Flask, abort, render_template, request, send_file

from .dataset import preview_csv
from .llm_pipeline import RunConfig, run_extraction
from .providers import ProviderError, make_provider


def repo_root() -> Path:
    return Path.cwd()


def local_models() -> list[Path]:
    models_dir = repo_root() / "models"
    if not models_dir.exists():
        return []
    return sorted(models_dir.glob("*.gguf"))


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
            summary=None,
            error=None,
            dataset_preview=None,
            dataset_download_url=None,
            zip_download_url=None,
            local_models=local_models(),
            default_openai_model=os.getenv("DPER_OPENAI_MODEL", "gpt-5.6-luna"),
            default_claude_model=os.getenv("DPER_CLAUDE_MODEL", "claude-sonnet-4-5"),
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
        provider_name = "default" if model_mode == "default" else request.form.get("llm_provider", "openai")
        api_key = request.form.get("api_key") or None
        model = request.form.get("model") or None
        local_model = None

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
            summary=summary,
            error=None,
            dataset_preview=dataset_preview,
            dataset_download_url=f"/download/{run_id}/dataset",
            zip_download_url=f"/download/{run_id}/all",
            local_models=local_models(),
            default_openai_model=os.getenv("DPER_OPENAI_MODEL", "gpt-5.6-luna"),
            default_claude_model=os.getenv("DPER_CLAUDE_MODEL", "claude-sonnet-4-5"),
            zip_size=zip_path.stat().st_size,
        )

    def _render_error(message: str):
        return (
            render_template(
                "index.html",
                summary=None,
                error=message,
                dataset_preview=None,
                dataset_download_url=None,
                zip_download_url=None,
                local_models=local_models(),
                default_openai_model=os.getenv("DPER_OPENAI_MODEL", "gpt-5.6-luna"),
                default_claude_model=os.getenv("DPER_CLAUDE_MODEL", "claude-sonnet-4-5"),
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
