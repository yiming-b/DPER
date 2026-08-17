#!/usr/bin/env python
from __future__ import annotations

import subprocess
import sys
import argparse
from pathlib import Path


def run(command: list[str], cwd: Path) -> None:
    print(f"\n> {' '.join(command)}")
    subprocess.check_call(command, cwd=cwd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install local DPER extras and download the recommended Qwen3 4B model.")
    parser.add_argument("--skip-install", action="store_true", help="Do not run pip install -e .[local].")
    parser.add_argument("--skip-download", action="store_true", help="Do not download the Qwen3 4B GGUF model.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if not args.skip_install:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], repo_root)
        run([sys.executable, "-m", "pip", "install", "-e", ".[local]"], repo_root)
    if not args.skip_download:
        run([sys.executable, str(repo_root / "scripts" / "download_qwen3_4b.py")], repo_root)
    print("\nLocal Qwen setup is ready.")
    print("Start the web UI with: python .\\scripts\\run_web.py")
    print("Or run CLI extraction with: python .\\scripts\\llm_extract.py --provider local-qwen --input \".\\reports\" --output \".\\output\\dper_qwen\"")


if __name__ == "__main__":
    main()
