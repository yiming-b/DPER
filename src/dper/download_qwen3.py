from __future__ import annotations

import argparse
from pathlib import Path

from .local_models import QWEN3_GGUF_MODELS, download_gguf_model, model_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download a local Qwen3 GGUF model for DPER.")
    parser.add_argument(
        "--model",
        choices=sorted(QWEN3_GGUF_MODELS),
        default="qwen3-4b",
        help="Model to download. Defaults to qwen3-4b.",
    )
    parser.add_argument("--output", default=None, help="Destination .gguf path. Defaults to models/<model filename>.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing local model file.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    model = QWEN3_GGUF_MODELS[args.model]
    destination = Path(args.output) if args.output else model_path(model)
    print(f"Model: {model.model_id}")
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

    path = download_gguf_model(args.model, destination, overwrite=args.overwrite, progress=progress)
    print(f"Ready: {path}")


if __name__ == "__main__":
    main()
