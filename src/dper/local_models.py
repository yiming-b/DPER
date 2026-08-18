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
    "qwen3-30b-a3b": GGUFModel(
        "qwen3-30b-a3b",
        "Qwen/Qwen3-30B-A3B-GGUF",
        "Qwen3-30B-A3B-Q4_K_M.gguf",
        label="Qwen3 30B-A3B MoE Q4_K_M",
        note="MoE model with 30.5B total and 3.3B activated parameters; practical on A100 40GB.",
    ),
    "qwen3-30b-a3b-q8": GGUFModel(
        "qwen3-30b-a3b-q8",
        "Qwen/Qwen3-30B-A3B-GGUF",
        "Qwen3-30B-A3B-Q8_0.gguf",
        quant="Q8_0",
        label="Qwen3 30B-A3B MoE Q8_0",
        note="Higher-precision MoE baseline; larger download and GPU memory use than Q4_K_M.",
    ),
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
    "deepseek-r1-llama-70b-q3": GGUFModel(
        "deepseek-r1-llama-70b-q3",
        "unsloth/DeepSeek-R1-Distill-Llama-70B-GGUF",
        "DeepSeek-R1-Distill-Llama-70B-Q3_K_M.gguf",
        quant="Q3_K_M",
        label="DeepSeek R1 Distill Llama 70B Q3_K_M",
        note="Large reasoning model; may need smaller chunks and may not fully offload on A100 40GB.",
    ),
    "deepseek-r1-llama-70b-q4": GGUFModel(
        "deepseek-r1-llama-70b-q4",
        "unsloth/DeepSeek-R1-Distill-Llama-70B-GGUF",
        "DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf",
        label="DeepSeek R1 Distill Llama 70B Q4_K_M",
        note="Very large for A100 40GB; expect partial CPU offload or reduce context.",
    ),
    "qwen2.5-72b-q3": GGUFModel(
        "qwen2.5-72b-q3",
        "bartowski/Qwen2.5-72B-Instruct-GGUF",
        "Qwen2.5-72B-Instruct-Q3_K_M.gguf",
        quant="Q3_K_M",
        label="Qwen2.5 72B Instruct Q3_K_M",
        note="Large instruct baseline; may need smaller chunks and may not fully offload on A100 40GB.",
    ),
    "qwen2.5-72b-q4": GGUFModel(
        "qwen2.5-72b-q4",
        "bartowski/Qwen2.5-72B-Instruct-GGUF",
        "Qwen2.5-72B-Instruct-Q4_K_M.gguf",
        label="Qwen2.5 72B Instruct Q4_K_M",
        note="Very large for A100 40GB; expect partial CPU offload or reduce context.",
    ),
    "llama3.3-70b-q3": GGUFModel(
        "llama3.3-70b-q3",
        "unsloth/Llama-3.3-70B-Instruct-GGUF",
        "Llama-3.3-70B-Instruct-Q3_K_M.gguf",
        quant="Q3_K_M",
        label="Llama 3.3 70B Instruct Q3_K_M",
        note="Large instruct baseline; check license terms before use.",
    ),
    "llama3.3-70b-q4": GGUFModel(
        "llama3.3-70b-q4",
        "unsloth/Llama-3.3-70B-Instruct-GGUF",
        "Llama-3.3-70B-Instruct-Q4_K_M.gguf",
        label="Llama 3.3 70B Instruct Q4_K_M",
        note="Very large for A100 40GB; check license terms and expect partial CPU offload.",
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
