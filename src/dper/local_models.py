from __future__ import annotations

from pathlib import Path
from typing import Callable

import requests

QWEN3_4B_REPO = "Qwen/Qwen3-4B-GGUF"
QWEN3_4B_QUANT = "Q4_K_M"
QWEN3_4B_FILENAME = "Qwen3-4B-Q4_K_M.gguf"
QWEN3_4B_MODEL_ID = f"{QWEN3_4B_REPO}:{QWEN3_4B_QUANT}"
QWEN3_4B_DOWNLOAD_URL = f"https://huggingface.co/{QWEN3_4B_REPO}/resolve/main/{QWEN3_4B_FILENAME}?download=true"


def default_models_dir(repo_root: Path | None = None) -> Path:
    return (repo_root or Path.cwd()) / "models"


def default_qwen_model_path(repo_root: Path | None = None) -> Path:
    return default_models_dir(repo_root) / QWEN3_4B_FILENAME


def download_qwen3_4b(
    destination: str | Path | None = None,
    *,
    overwrite: bool = False,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    target = Path(destination) if destination else default_qwen_model_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        return target

    tmp_path = target.with_suffix(target.suffix + ".download")
    if tmp_path.exists():
        tmp_path.unlink()

    with requests.get(QWEN3_4B_DOWNLOAD_URL, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length") or 0) or None
        downloaded = 0
        with tmp_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)

    tmp_path.replace(target)
    return target
