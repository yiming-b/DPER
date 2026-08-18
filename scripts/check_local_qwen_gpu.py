#!/usr/bin/env python
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dper.local_models import default_qwen_model_path
from dper.providers import LocalGGUFProvider


def run_nvidia_smi() -> None:
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            check=False,
            text=True,
            capture_output=True,
            timeout=15,
        )
    except FileNotFoundError:
        print("nvidia-smi: not found")
        return
    except subprocess.TimeoutExpired:
        print("nvidia-smi: timed out")
        return
    print("nvidia-smi:")
    print(result.stdout.strip() or result.stderr.strip())


def main() -> None:
    model_path = default_qwen_model_path(Path.cwd())
    if not model_path.exists():
        raise SystemExit(f"Model file not found: {model_path}")

    os.environ.setdefault("DPER_LOCAL_GPU_LAYERS", "-1")
    os.environ.setdefault("DPER_LOCAL_N_CTX", "4096")
    os.environ.setdefault("DPER_LOCAL_MAX_TOKENS", "128")
    os.environ.setdefault("DPER_LOCAL_VERBOSE", "1")

    print(f"Python: {sys.executable}")
    print(f"Model: {model_path}")
    print(f"CUDA_VISIBLE_DEVICES={os.getenv('CUDA_VISIBLE_DEVICES', '')}")
    print(f"NVIDIA_VISIBLE_DEVICES={os.getenv('NVIDIA_VISIBLE_DEVICES', '')}")
    run_nvidia_smi()

    provider = LocalGGUFProvider(model_path)
    print(provider.runtime_summary)
    print("Running one short generation...")
    text = provider.generate(
        "Return JSON only.",
        'Return {"gpu_check":"ok"} as JSON. Do not add anything else.',
    )
    print(text[:1000])


if __name__ == "__main__":
    main()
