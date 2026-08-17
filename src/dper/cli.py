from __future__ import annotations

import argparse
import json
from pathlib import Path

from .llm_pipeline import RunConfig, run_extraction
from .providers import ProviderError, make_provider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract dog phenotypes from veterinary PDF reports with an LLM.")
    parser.add_argument("--input", required=True, help="PDF file or folder of PDF reports.")
    parser.add_argument("--output", required=True, help="Output directory for CSV tables.")
    parser.add_argument("--provider", choices=["default", "openai", "claude", "local-qwen", "local", "dry-run"], default="default")
    parser.add_argument("--api-key", default=None, help="API key for OpenAI or Claude. Prefer environment variables for routine use.")
    parser.add_argument("--model", default=None, help="Provider model id. Defaults come from environment or package defaults.")
    parser.add_argument("--local-model", default=None, help="Path to a local .gguf model. Optional for --provider local-qwen after setup.")
    parser.add_argument("--dictionary", default=None, help="Path to phenotype_dictionary.csv.")
    parser.add_argument("--append", action="store_true", help="Append to existing output tables and skip reports already in run_manifest.json.")
    parser.add_argument("--chunk-chars", type=int, default=18000, help="Approximate report text characters per LLM call.")
    parser.add_argument("--max-dictionary-rows", type=int, default=120, help="Dictionary rows supplied to each LLM chunk.")
    parser.add_argument("--no-redact", action="store_true", help="Do not redact phones, emails, and simple street-address patterns before API calls.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        provider = make_provider(args.provider, api_key=args.api_key, model=args.model, local_model=args.local_model)
    except ProviderError as exc:
        raise SystemExit(str(exc)) from exc
    summary = run_extraction(
        RunConfig(
            input_path=Path(args.input),
            output_dir=Path(args.output),
            provider=provider,
            dictionary_path=Path(args.dictionary) if args.dictionary else None,
            append=args.append,
            chunk_chars=args.chunk_chars,
            max_dictionary_rows=args.max_dictionary_rows,
            redact=not args.no_redact,
        )
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
