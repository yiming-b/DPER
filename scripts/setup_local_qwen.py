#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    print(f"\n> {' '.join(command)}")
    subprocess.check_call(command, cwd=cwd, env=env)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install local DPER extras and download the recommended Qwen3 4B model.")
    parser.add_argument("--skip-install", action="store_true", help="Do not run pip install -e .[local].")
    parser.add_argument("--skip-download", action="store_true", help="Do not download the Qwen3 4B GGUF model.")
    parser.add_argument("--cuda", action="store_true", help="Reinstall llama-cpp-python with CUDA support for NVIDIA GPUs.")
    parser.add_argument(
        "--cuda-wheel",
        choices=["cu118", "cu121", "cu122", "cu123", "cu124", "cu125", "cu130", "cu132"],
        default=None,
        help="Install a prebuilt llama-cpp-python CUDA wheel from the matching CUDA wheel index.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    local_env = os.environ.copy()
    local_env["PIP_CACHE_DIR"] = str(repo_root / ".pip_cache")
    local_env["HF_HOME"] = str(repo_root / ".hf_cache")
    Path(local_env["PIP_CACHE_DIR"]).mkdir(exist_ok=True)
    Path(local_env["HF_HOME"]).mkdir(exist_ok=True)
    if not args.skip_install:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], repo_root, local_env)
        run([sys.executable, "-m", "pip", "install", "-e", ".[local]"], repo_root, local_env)
    if args.cuda or args.cuda_wheel:
        if args.cuda_wheel:
            run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--force-reinstall",
                    "--no-cache-dir",
                    "llama-cpp-python",
                    "--extra-index-url",
                    f"https://abetlen.github.io/llama-cpp-python/whl/{args.cuda_wheel}",
                ],
                repo_root,
                local_env,
            )
        else:
            cuda_env = local_env.copy()
            cuda_env["CMAKE_ARGS"] = "-DGGML_CUDA=on"
            cuda_env["FORCE_CMAKE"] = "1"
            run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--force-reinstall",
                    "--no-cache-dir",
                    "llama-cpp-python",
                ],
                repo_root,
                cuda_env,
            )
    if not args.skip_download:
        run([sys.executable, str(repo_root / "scripts" / "download_qwen3_4b.py")], repo_root, local_env)
    if os.name == "nt":
        web_command = "python .\\scripts\\run_web.py"
        cli_command = 'python .\\scripts\\llm_extract.py --provider local-qwen --input ".\\reports" --output ".\\output\\dper_qwen"'
        gpu_check_command = "python .\\scripts\\check_local_qwen_gpu.py"
    else:
        web_command = "python scripts/run_web.py"
        cli_command = 'python scripts/llm_extract.py --provider local-qwen --input "./reports" --output "./output/dper_qwen"'
        gpu_check_command = "python scripts/check_local_qwen_gpu.py"
    print("\nLocal Qwen setup is ready.")
    print(f"Virtual environment should be inside: {repo_root / '.venv'}")
    print(f"Package cache: {local_env['PIP_CACHE_DIR']}")
    print(f"Model files: {repo_root / 'models'}")
    print(f"Check local Qwen/GPU setup with: {gpu_check_command}")
    print(f"Start the web UI with: {web_command}")
    print(f"Or run CLI extraction with: {cli_command}")


if __name__ == "__main__":
    main()
