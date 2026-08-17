# DPER

DPER extracts dog phenotype information from heterogeneous veterinary PDF reports into auditable CSV tables.

The package supports:

- OpenAI API extraction
- Claude API extraction
- Optional local GGUF model extraction
- A browser UI for uploading PDFs and downloading CSV output
- A CLI for batch runs
- A controlled phenotype dictionary in `schemas/phenotype_dictionary.csv`

Raw sample reports and generated patient-level outputs are intentionally excluded from Git. They often contain private source-record content.

## Output Tables

Each run writes:

- `dataset.csv`
- `dog_summary.csv`
- `visit_summary.csv`
- `phenotype_events.csv`
- `lab_results.csv`
- `diagnostic_events.csv`
- `medication_events.csv`
- `procedure_events.csv`
- `new_candidate_phenotypes.csv`
- `run_manifest.json`
- `summary.json`

Use `phenotype_id` as the stable machine key. The dictionary column `field_or_phenotype` is a human-readable label and may overlap with `phenotype_id`.

## Install

```powershell
git clone https://github.com/yiming-b/DPER.git
cd DPER
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## API Key Setup

The UI accepts an API key for a single run and does not save it. For CLI use, environment variables are more convenient.

OpenAI:

```powershell
setx OPENAI_API_KEY "your_openai_key"
```

Claude:

```powershell
setx ANTHROPIC_API_KEY "your_anthropic_key"
```

Open a new terminal after `setx`.

Optional model defaults:

```powershell
setx DPER_OPENAI_MODEL "gpt-5.6-luna"
setx DPER_CLAUDE_MODEL "claude-sonnet-4-5"
```

You can also pass a model id in the UI or with `--model`.

## Run The Web UI

Hosted browser app:

https://dper-dog-phenotypes.ybyb1234.chatgpt.site

The `site/` folder contains a deployable browser version of DPER. It lets users upload multiple PDFs, choose the built-in extractor or provide an OpenAI/Claude API key, use the default phenotype list or provide a custom comma-separated / one-per-line phenotype list, preview `dataset.csv`, and download it directly.

Local Python UI:

```powershell
python .\scripts\run_web.py
```

Open:

```text
http://127.0.0.1:7860
```

In the UI:

1. Choose the default built-in extractor or API-backed LLM extraction.
2. If using an API-backed LLM, choose OpenAI or Claude and enter an API key.
3. Upload one or more PDF reports.
4. Generate `dataset.csv`.
5. Preview `dataset.csv` in the page and download it directly.

The UI redacts common phone numbers, emails, and simple street-address patterns before API calls by default.

## Run From CLI

Default built-in extractor:

```powershell
python .\scripts\llm_extract.py --provider default --input "C:\path\to\reports" --output .\output\dper_default
```

OpenAI:

```powershell
python .\scripts\llm_extract.py --provider openai --input "C:\path\to\reports" --output .\output\dper_openai
```

Claude:

```powershell
python .\scripts\llm_extract.py --provider claude --input "C:\path\to\reports" --output .\output\dper_claude
```

Pass an API key directly only for temporary use:

```powershell
python .\scripts\llm_extract.py --provider openai --api-key "your_key" --input ".\reports" --output ".\output"
```

Append new reports to an existing output folder:

```powershell
python .\scripts\llm_extract.py --provider openai --input "C:\path\to\new_reports" --output .\output\dper_openai --append
```

Append mode skips reports already present in `run_manifest.json` by SHA-256 hash.

## Local Model Mode

No local model is included in this repository. Large model files should not be committed.

To use local mode:

1. Install the optional runtime:

```powershell
python -m pip install -e ".[local]"
```

2. Place a compatible instruct `.gguf` model under `models/`, for example:

```text
models\your-instruct-model.gguf
```

3. Run:

```powershell
python .\scripts\llm_extract.py --provider local --local-model .\models\your-instruct-model.gguf --input ".\reports" --output ".\output\dper_local"
```

Local model quality depends heavily on the model. For best results, start with API mode, then benchmark local models on a reviewed subset.

## Repository Layout

```text
src/dper/                 Python package
src/dper/web_app.py       Flask app
src/dper/llm_pipeline.py  LLM extraction runner and CSV flattening
src/dper/providers.py     OpenAI, Claude, local GGUF provider interface
schemas/                  Controlled phenotype schema
scripts/                  CLI and web entrypoints
docs/                     Design notes and prompt template
```

## Privacy Notes

- Do not commit raw report PDFs.
- Do not commit generated patient-level CSVs unless they are approved for sharing.
- API mode sends extracted, redacted report text chunks to the selected model provider.
- API keys are not stored by the web UI.
- Review `new_candidate_phenotypes.csv` before expanding the dictionary.

## Development Checks

```powershell
python -m py_compile .\src\dper\*.py .\scripts\llm_extract.py .\scripts\run_web.py
python .\scripts\llm_extract.py --provider dry-run --input "C:\path\to\one_report.pdf" --output .\tmp\dry_run
```
