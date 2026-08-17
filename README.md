# DPER

DPER extracts dog phenotype information from heterogeneous veterinary PDF reports into auditable CSV tables.

The package supports:

- Local Qwen3 4B GGUF extraction with no API key
- Built-in regex/dictionary extraction with no model download
- OpenAI API extraction
- Claude API extraction
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

Recommended local setup, no API key:

Windows PowerShell:

```powershell
git clone https://github.com/yiming-b/DPER.git
cd DPER
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python .\scripts\setup_local_qwen.py
python .\scripts\run_web.py
```

Linux/macOS:

```bash
git clone https://github.com/yiming-b/DPER.git
cd DPER
python3 -m venv .venv
source .venv/bin/activate
python scripts/setup_local_qwen.py
python scripts/run_web.py
```

Then open:

```text
http://127.0.0.1:7860
```

These commands intentionally keep the working environment inside the `DPER` folder:

- Python packages install into `DPER/.venv/`.
- Qwen and other local model files are stored in `DPER/models/`.
- The setup script uses `DPER/.pip_cache/` and `DPER/.hf_cache/` for its own install/download cache.

Optional, for later manual commands in the same terminal, set cache folders explicitly.

Windows PowerShell:

```powershell
$env:PIP_CACHE_DIR = "$PWD\.pip_cache"
$env:HF_HOME = "$PWD\.hf_cache"
```

Linux/macOS:

```bash
export PIP_CACHE_DIR="$PWD/.pip_cache"
export HF_HOME="$PWD/.hf_cache"
```

Full CLI command for local Qwen mode:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider local-qwen --input ".\reports" --output ".\output\dper_qwen"
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider local-qwen --input "./reports" --output "./output/dper_qwen"
```

Minimal install without downloading Qwen:

Windows PowerShell:

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
```

Linux/macOS:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

## Run The Web UI

Hosted browser app:

https://dper-dog-phenotypes.ybyb1234.chatgpt.site

The `site/` folder contains a deployable browser version of DPER. It lets users upload multiple PDFs, choose the built-in extractor or provide an OpenAI/Claude API key, select individual default identity fields, select individual default phenotype columns, provide a custom comma-separated / one-per-line phenotype list, preview `dataset.csv`, and download it directly. Custom phenotype columns are placed before default phenotype columns; duplicate default phenotypes are removed automatically.

The hosted browser app displays the default/local model catalog. Its default run uses the browser-based regex/dictionary extractor. Qwen3 4B and other downloaded GGUF models require the local Python backend because the hosted page cannot inspect or run multi-GB model files on a user's computer.

The browser dataset includes dog identity and demographic columns such as `dog_name`, `patient_id`, `species`, `breed_raw`, `sex`, `reproductive_status`, `color`, `weight`, `date_of_birth`, and `visit_dates`. Owner/client contact information is intentionally excluded. When a single PDF contains multiple visits for the same dog, DPER keeps one row for the file and stores visit dates inside phenotype cells or changed demographic fields as JSON objects with `MM/DD/YYYY` dates.

Local Python UI:

Windows PowerShell:

```powershell
python .\scripts\run_web.py
```

Linux/macOS:

```bash
python scripts/run_web.py
```

Open:

```text
http://127.0.0.1:7860
```

In the local UI:

1. Use the default/local extractor list. Qwen3 4B is selected automatically when it has been downloaded.
2. Select the default identity fields and default phenotype columns to include.
3. Optionally paste or upload a `.txt` phenotype list. Use one phenotype per line or separate entries with commas; custom phenotype columns appear before defaults and duplicate defaults are removed.
4. Upload one or more PDF reports.
5. Generate `dataset.csv`.
6. Preview `dataset.csv` in the page and download it directly.
7. Use OpenAI or Claude only if you want an API-backed run.

The UI redacts common phone numbers, emails, and simple street-address patterns before model calls by default.

Local Qwen runs happen inside the Python backend, not inside the browser. The page shows a running message after submission; a Qwen run can take several minutes per report depending on CPU/RAM and report length.

## Run From CLI

Recommended local Qwen mode:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider local-qwen --input ".\reports" --output ".\output\dper_qwen"
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider local-qwen --input "./reports" --output "./output/dper_qwen"
```

Default built-in extractor:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider default --input "C:\path\to\reports" --output .\output\dper_default
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider default --input "/path/to/reports" --output ./output/dper_default
```

OpenAI:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider openai --input "C:\path\to\reports" --output .\output\dper_openai
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider openai --input "/path/to/reports" --output ./output/dper_openai
```

Claude:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider claude --input "C:\path\to\reports" --output .\output\dper_claude
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider claude --input "/path/to/reports" --output ./output/dper_claude
```

Pass an API key directly only for temporary use:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider openai --api-key "your_key" --input ".\reports" --output ".\output"
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider openai --api-key "your_key" --input "./reports" --output "./output"
```

Append new reports to an existing output folder:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider openai --input "C:\path\to\new_reports" --output .\output\dper_openai --append
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider openai --input "/path/to/new_reports" --output ./output/dper_openai --append
```

Append mode skips reports already present in `run_manifest.json` by SHA-256 hash.

## API Key Setup

API-backed extraction is optional. The UI accepts an API key for a single run and does not save it. For CLI use, environment variables are more convenient.

OpenAI:

Windows PowerShell:

```powershell
setx OPENAI_API_KEY "your_openai_key"
```

Linux/macOS:

```bash
export OPENAI_API_KEY="your_openai_key"
```

Claude:

Windows PowerShell:

```powershell
setx ANTHROPIC_API_KEY "your_anthropic_key"
```

Linux/macOS:

```bash
export ANTHROPIC_API_KEY="your_anthropic_key"
```

On Windows, open a new terminal after `setx`.

Optional model defaults:

Windows PowerShell:

```powershell
setx DPER_OPENAI_MODEL "gpt-5.6-luna"
setx DPER_CLAUDE_MODEL "claude-sonnet-5"
```

Linux/macOS:

```bash
export DPER_OPENAI_MODEL="gpt-5.6-luna"
export DPER_CLAUDE_MODEL="claude-sonnet-5"
```

You can select a supported model from the UI dropdown or pass a model id with `--model`.

## Local Qwen3 4B Mode

No API key is required for local Qwen mode. No local model is committed to this repository; large model files should stay in `models/` and are ignored by Git.

When you run the recommended setup from inside the cloned `DPER` folder, the virtual environment, package cache, Hugging Face cache, and model files all stay under that same folder.

The local Python UI lists:

- Built-in regex/dictionary extractor, always available.
- Recommended Qwen3 4B GGUF model, marked as downloaded or missing.
- Any other `.gguf` files found in `models/`.

For the recommended public Qwen3 4B GGUF download, users do not need a Hugging Face account or token. A Hugging Face account/token is only needed for gated or private model repositories, such as some Llama-family distributions or privately hosted model files.

To manually set up the recommended Qwen3 4B GGUF model:

One-command setup:

Windows PowerShell:

```powershell
python .\scripts\setup_local_qwen.py
```

Linux/macOS:

```bash
python scripts/setup_local_qwen.py
```

Or run the steps separately.

1. Install the optional runtime:

```powershell
python -m pip install -e ".[local]"
```

2. Download the recommended model into `models/`:

```powershell
dper-download-qwen3
```

From a source checkout, this equivalent script also works:

Windows PowerShell:

```powershell
python .\scripts\download_qwen3_4b.py
```

Linux/macOS:

```bash
python scripts/download_qwen3_4b.py
```

This downloads `Qwen/Qwen3-4B-GGUF:Q4_K_M` to:

```powershell
.\models\Qwen3-4B-Q4_K_M.gguf
```

On Linux/macOS, the same file is:

```bash
./models/Qwen3-4B-Q4_K_M.gguf
```

3. Run from the local web UI, where Qwen3 4B is auto-selected when downloaded, or run from CLI:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider local-qwen --input ".\reports" --output ".\output\dper_qwen"
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider local-qwen --input "./reports" --output "./output/dper_qwen"
```

To use a different local instruct `.gguf` model:

Windows PowerShell:

```powershell
python .\scripts\llm_extract.py --provider local --local-model .\models\your-instruct-model.gguf --input ".\reports" --output ".\output\dper_local"
```

Linux/macOS:

```bash
python scripts/llm_extract.py --provider local --local-model ./models/your-instruct-model.gguf --input "./reports" --output "./output/dper_local"
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

Windows PowerShell:

```powershell
$files = @(Get-ChildItem -Recurse .\src, .\scripts -Filter *.py | Select-Object -ExpandProperty FullName)
python -m py_compile @files
python .\scripts\setup_local_qwen.py --help
python .\scripts\llm_extract.py --provider dry-run --input "C:\path\to\one_report.pdf" --output .\tmp\dry_run
```

Linux/macOS:

```bash
python -m py_compile $(find src scripts -name "*.py")
python scripts/setup_local_qwen.py --help
python scripts/llm_extract.py --provider dry-run --input "/path/to/one_report.pdf" --output ./tmp/dry_run
```
