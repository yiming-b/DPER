from __future__ import annotations

import argparse
from pathlib import Path

from .local_models import GGUF_MODEL_PRESETS, default_models_dir, download_gguf_model, download_hf_file, model_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download a local GGUF language model for DPER.")
    parser.add_argument(
        "--model",
        choices=sorted(GGUF_MODEL_PRESETS),
        default="qwen3-4b",
        help="Preset model to download. Defaults to qwen3-4b.",
    )
    parser.add_argument("--list-models", action="store_true", help="List preset model keys and exit.")
    parser.add_argument("--repo", default=None, help="Custom Hugging Face repo id, for example owner/model-GGUF.")
    parser.add_argument("--filename", default=None, help="Custom .gguf filename inside --repo.")
    parser.add_argument("--output", default=None, help="Destination .gguf path. Defaults to models/<model filename>.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing local model file.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.list_models:
        for key, model in GGUF_MODEL_PRESETS.items():
            suffix = f" - {model.note}" if model.note else ""
            print(f"{key}: {model.label or model.filename} ({model.model_id}){suffix}")
        return

    if args.repo or args.filename:
        if not args.repo or not args.filename:
            parser.error("--repo and --filename must be provided together.")
        destination = Path(args.output) if args.output else default_models_dir() / Path(args.filename).name
        model_label = f"{args.repo}:{args.filename}"
        repo = args.repo
        filename = args.filename
        model_key = None
    else:
        model = GGUF_MODEL_PRESETS[args.model]
        destination = Path(args.output) if args.output else model_path(model)
        model_label = model.model_id
        repo = model.repo
        filename = model.filename
        model_key = args.model

    print(f"Model: {model_label}")
    print(f"Destination: {destination}")
    last_reported = -1

    def progress(downloaded: int, total: int | None) -> None:
        nonlocal last_reported
        if total:
            percent = int(downloaded * 100 / total)
            if percent >= last_reported + 5 or percent == 100:
                last_reported = percent
                print(f"Downloaded {percent}%")
        elif downloaded // (512 * 1024 * 1024) > last_reported:
            last_reported = downloaded // (512 * 1024 * 1024)
            print(f"Downloaded {downloaded / (1024 * 1024 * 1024):.1f} GB")

    if model_key:
        path = download_gguf_model(model_key, destination, overwrite=args.overwrite, progress=progress)
    else:
        path = download_hf_file(repo=repo, filename=filename, destination=destination, overwrite=args.overwrite, progress=progress)
    print(f"Ready: {path}")


if __name__ == "__main__":
    main()
