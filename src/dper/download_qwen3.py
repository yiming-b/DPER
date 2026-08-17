from __future__ import annotations

import argparse
from pathlib import Path

from .local_models import QWEN3_4B_MODEL_ID, default_qwen_model_path, download_qwen3_4b


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download the recommended local Qwen3 4B GGUF model for DPER.")
    parser.add_argument("--output", default=None, help="Destination .gguf path. Defaults to models/Qwen3-4B-Q4_K_M.gguf.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing local model file.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    destination = Path(args.output) if args.output else default_qwen_model_path()
    print(f"Model: {QWEN3_4B_MODEL_ID}")
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

    path = download_qwen3_4b(destination, overwrite=args.overwrite, progress=progress)
    print(f"Ready: {path}")


if __name__ == "__main__":
    main()
