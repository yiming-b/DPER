#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dper.local_models import default_qwen_model_path
from dper.providers import llama_supports_gpu_offload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check whether local Qwen/llama-cpp-python is using GPU offload.")
    parser.add_argument("--n-ctx", type=int, default=512, help="Small context used for this diagnostic.")
    parser.add_argument("--max-tokens", type=int, default=8, help="Tiny completion size used for this diagnostic.")
    parser.add_argument("--n-gpu-layers", type=int, default=-1, help="GPU layers to offload; -1 means all possible layers.")
    parser.add_argument("--timeout", type=int, default=120, help="Seconds allowed for the tiny generation test.")
    parser.add_argument("--skip-generate", action="store_true", help="Only check package/backend/model loading.")
    return parser


def run_nvidia_smi(label: str) -> None:
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            check=False,
            text=True,
            capture_output=True,
            timeout=15,
        )
    except FileNotFoundError:
        print(f"{label}: nvidia-smi not found")
        return
    except subprocess.TimeoutExpired:
        print(f"{label}: nvidia-smi timed out")
        return
    print(f"{label}: nvidia-smi")
    print(result.stdout.strip() or result.stderr.strip())


@contextmanager
def generation_timeout(seconds: int) -> Iterator[None]:
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def handler(signum, frame):  # type: ignore[no-untyped-def]
        raise TimeoutError(f"Generation did not finish within {seconds} seconds.")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def main() -> None:
    args = build_parser().parse_args()
    model_path = default_qwen_model_path(Path.cwd())
    if not model_path.exists():
        raise SystemExit(f"Model file not found: {model_path}")

    print(f"Python: {sys.executable}")
    print(f"Model: {model_path}")
    print(f"CUDA_VISIBLE_DEVICES={os.getenv('CUDA_VISIBLE_DEVICES', '')}")
    print(f"NVIDIA_VISIBLE_DEVICES={os.getenv('NVIDIA_VISIBLE_DEVICES', '')}")
    run_nvidia_smi("before load")

    try:
        import llama_cpp
        from llama_cpp import Llama
    except Exception as exc:
        raise SystemExit(f"Could not import llama-cpp-python: {exc}") from exc

    print(f"llama_cpp package: {getattr(llama_cpp, '__file__', 'unknown')}")
    print(f"llama_cpp version: {getattr(llama_cpp, '__version__', 'unknown')}")
    gpu_support = llama_supports_gpu_offload()
    print(f"llama_supports_gpu_offload={gpu_support}")
    if args.n_gpu_layers != 0 and gpu_support is False:
        raise SystemExit(
            "This llama-cpp-python install reports no GPU offload support. "
            "Reinstall with a CUDA wheel or CUDA source build before running DPER Qwen."
        )

    print(
        "Loading model with "
        f"n_gpu_layers={args.n_gpu_layers}, n_ctx={args.n_ctx}, max_tokens={args.max_tokens}, verbose=True"
    )
    started = time.time()
    llm = Llama(
        model_path=str(model_path),
        n_gpu_layers=args.n_gpu_layers,
        n_ctx=args.n_ctx,
        n_threads=max(1, min(os.cpu_count() or 4, 8)),
        verbose=True,
    )
    print(f"Model loaded in {time.time() - started:.1f}s")
    run_nvidia_smi("after load")

    if args.skip_generate:
        print("Skipping generation by request.")
        return

    print("Running tiny raw completion...")
    started = time.time()
    with generation_timeout(args.timeout):
        result = llm(
            'Complete this exact JSON: {"gpu_check":"',
            max_tokens=args.max_tokens,
            temperature=0.0,
            echo=False,
            stop=["\n", "}"],
        )
    print(f"Generation finished in {time.time() - started:.1f}s")
    print(result["choices"][0]["text"][:1000])
    run_nvidia_smi("after generation")


if __name__ == "__main__":
    main()
