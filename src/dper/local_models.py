from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class GGUFModel:
    key: str
    repo: str
    filename: str
    quant: str = "Q4_K_M"
    label: str = ""
    note: str = ""

    @property
    def model_id(self) -> str:
        return f"{self.repo}:{self.quant}"

    @property
    def download_url(self) -> str:
        repo = quote(self.repo, safe="/")
        filename = quote(self.filename, safe="/")
        return f"https://huggingface.co/{repo}/resolve/main/{filename}?download=true"


GGUF_MODEL_PRESETS = {
    "qwen3-4b": GGUFModel("qwen3-4b", "Qwen/Qwen3-4B-GGUF", "Qwen3-4B-Q4_K_M.gguf", label="Qwen3 4B Q4_K_M"),
    "qwen3-8b": GGUFModel("qwen3-8b", "Qwen/Qwen3-8B-GGUF", "Qwen3-8B-Q4_K_M.gguf", label="Qwen3 8B Q4_K_M"),
    "qwen3-14b": GGUFModel("qwen3-14b", "Qwen/Qwen3-14B-GGUF", "Qwen3-14B-Q4_K_M.gguf", label="Qwen3 14B Q4_K_M"),
    "qwen3-32b": GGUFModel("qwen3-32b", "Qwen/Qwen3-32B-GGUF", "Qwen3-32B-Q4_K_M.gguf", label="Qwen3 32B Q4_K_M"),
    "deepseek-r1-qwen-14b": GGUFModel(
        "deepseek-r1-qwen-14b",
        "unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF",
        "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
        label="DeepSeek R1 Distill Qwen 14B Q4_K_M",
        note="Reasoning model; may be slower and more verbose than instruct models.",
    ),
    "deepseek-r1-qwen-32b": GGUFModel(
        "deepseek-r1-qwen-32b",
        "unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF",
        "DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf",
        label="DeepSeek R1 Distill Qwen 32B Q4_K_M",
        note="Reasoning model; try only after 14B on a single A100 40GB.",
    ),
    "mistral-small-24b": GGUFModel(
        "mistral-small-24b",
        "unsloth/Mistral-Small-24B-Instruct-2501-GGUF",
        "Mistral-Small-24B-Instruct-2501-Q4_K_M.gguf",
        label="Mistral Small 24B Instruct Q4_K_M",
        note="Good non-Qwen instruct baseline.",
    ),
    "gemma-3-27b": GGUFModel(
        "gemma-3-27b",
        "google/gemma-3-27b-it-qat-q4_0-gguf",
        "gemma-3-27b-it-q4_0.gguf",
        quant="Q4_0",
        label="Gemma 3 27B IT QAT Q4_0",
        note="Gated on Hugging Face; requires accepting Google's license and setting HF_TOKEN.",
    ),
}

QWEN3_GGUF_MODELS = GGUF_MODEL_PRESETS
QWEN3_4B_REPO = GGUF_MODEL_PRESETS["qwen3-4b"].repo
QWEN3_4B_QUANT = GGUF_MODEL_PRESETS["qwen3-4b"].quant
QWEN3_4B_FILENAME = GGUF_MODEL_PRESETS["qwen3-4b"].filename
QWEN3_4B_MODEL_ID = GGUF_MODEL_PRESETS["qwen3-4b"].model_id
QWEN3_4B_DOWNLOAD_URL = GGUF_MODEL_PRESETS["qwen3-4b"].download_url


def default_models_dir(repo_root: Path | None = None) -> Path:
    return (repo_root or Path.cwd()) / "models"


def default_qwen_model_path(repo_root: Path | None = None) -> Path:
    return default_models_dir(repo_root) / QWEN3_4B_FILENAME


def model_path(model: GGUFModel, repo_root: Path | None = None) -> Path:
    return default_models_dir(repo_root) / model.filename


def download_hf_file(
    *,
    repo: str,
    filename: str,
    destination: str | Path,
    overwrite: bool = False,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        return target

    tmp_path = target.with_suffix(target.suffix + ".download")
    if tmp_path.exists():
        tmp_path.unlink()

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else None
    url = f"https://huggingface.co/{quote(repo, safe='/')}/resolve/main/{quote(filename, safe='/')}?download=true"
    with requests.get(url, headers=headers, stream=True, timeout=60) as response:
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


def download_gguf_model(
    model_key: str,
    destination: str | Path | None = None,
    *,
    overwrite: bool = False,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    model = GGUF_MODEL_PRESETS[model_key]
    target = Path(destination) if destination else model_path(model)
    return download_hf_file(
        repo=model.repo,
        filename=model.filename,
        destination=target,
        overwrite=overwrite,
        progress=progress,
    )


def download_qwen3_4b(
    destination: str | Path | None = None,
    *,
    overwrite: bool = False,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    return download_gguf_model("qwen3-4b", destination, overwrite=overwrite, progress=progress)
