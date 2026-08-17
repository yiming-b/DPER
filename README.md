# DPER

DPER extracts dog phenotype information from heterogeneous veterinary PDF reports into auditable CSV tables.

The package supports:

- OpenAI API extraction
- Claude API extraction
- Optional local Qwen3 4B GGUF model extraction with no API key
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
setx DPER_CLAUDE_MODEL "claude-sonnet-5"
```

You can select a supported model from the UI dropdown or pass a model id with `--model`.

## Run The Web UI

Hosted browser app:

https://dper-dog-phenotypes.ybyb1234.chatgpt.site

The `site/` folder contains a deployable browser version of DPER. It lets users upload multiple PDFs, choose the built-in extractor or provide an OpenAI/Claude API key, select individual default identity fields, select individual default phenotype columns, provide a custom comma-separated / one-per-line phenotype list, preview `dataset.csv`, and download it directly. Custom phenotype columns are placed before default phenotype columns; duplicate default phenotypes are removed automatically.

The hosted browser app displays the default/local model catalog. Its default run uses the browser-based regex/dictionary extractor. Qwen3 4B and other downloaded GGUF models require the local Python backend because the hosted page cannot inspect or run multi-GB model files on a user's computer.

The browser dataset includes dog identity and demographic columns such as `dog_name`, `patient_id`, `species`, `breed_raw`, `sex`, `reproductive_status`, `color`, `weight`, `date_of_birth`, and `visit_dates`. Owner/client contact information is intentionally excluded. When a single PDF contains multiple visits for the same dog, DPER keeps one row for the file and stores visit dates inside phenotype cells or changed demographic fields as JSON objects with `MM/DD/YYYY` dates.

Local Python UI:

```powershell
python .\scripts\run_web.py
```

Open:

```text
http://127.0.0.1:7860
```

In the UI:

1. Choose the default/local extractor list or API-backed LLM extraction.
2. If using Local Qwen3 4B, install the local runtime and download the model once as shown below.
3. If using an API-backed LLM, choose OpenAI or Claude and enter an API key.
4. Upload one or more PDF reports.
5. Generate `dataset.csv`.
6. Preview `dataset.csv` in the page and download it directly.

The UI redacts common phone numbers, emails, and simple street-address patterns before model calls by default.

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

## Local Qwen3 4B Mode

No API key is required for local Qwen mode. No local model is committed to this repository; large model files should stay in `models/` and are ignored by Git.

The local Python UI lists:

- Built-in regex/dictionary extractor, always available.
- Recommended Qwen3 4B GGUF model, marked as downloaded or missing.
- Any other `.gguf` files found in `models/`.

For the recommended public Qwen3 4B GGUF download, users do not need a Hugging Face account or token. A Hugging Face account/token is only needed for gated or private model repositories, such as some Llama-family distributions or privately hosted model files.

To use the recommended Qwen3 4B GGUF model:

1. Install the optional runtime:

```powershell
python -m pip install -e ".[local]"
```

2. Download the recommended model into `models/`:

```powershell
dper-download-qwen3
```

From a source checkout, this equivalent script also works:

```powershell
python .\scripts\download_qwen3_4b.py
```

This downloads `Qwen/Qwen3-4B-GGUF:Q4_K_M` to:

```powershell
.\models\Qwen3-4B-Q4_K_M.gguf
```

3. Run from the local web UI and choose `Local Qwen3 4B`, or run from CLI:

```powershell
python .\scripts\llm_extract.py --provider local-qwen --input ".\reports" --output ".\output\dper_qwen"
```

To use a different local instruct `.gguf` model:

```powershell
python .\scripts\llm_extract.py --provider local --local-model .\models\your-instruct-model.gguf --input ".\reports" --output ".\output\dper_local"
```

Local model quality depends heavily on the model and computer speed. For best results, benchmark Qwen3 4B against a reviewed subset of reports before processing a large folder.

## Repository Layout

```text
src/dper/                 Python package
src/dper/web_app.py       Flask app
src/dper/llm_pipeline.py  LLM extraction runner and CSV flattening
src/dper/providers.py     OpenAI, Claude, local GGUF provider interface
src/dper/local_models.py  Local Qwen3 4B model metadata and downloader
schemas/                  Controlled phenotype schema
scripts/                  CLI and web entrypoints
docs/                     Design notes and prompt template
```

## Privacy Notes

- Do not commit raw report PDFs.
- Do not commit generated patient-level CSVs unless they are approved for sharing.
- API mode sends extracted, redacted report text chunks to the selected model provider.
- Local Qwen mode keeps model inference on the user's computer.
- API keys are not stored by the web UI.
- Review `new_candidate_phenotypes.csv` before expanding the dictionary.

## Development Checks

```powershell
$files = @(Get-ChildItem -Recurse .\src, .\scripts -Filter *.py | Select-Object -ExpandProperty FullName)
python -m py_compile @files
python .\scripts\llm_extract.py --provider dry-run --input "C:\path\to\one_report.pdf" --output .\tmp\dry_run
```
