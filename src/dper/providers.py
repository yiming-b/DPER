from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


class ProviderError(RuntimeError):
    pass


@dataclass
class LLMProvider:
    model: str

    def generate(self, system_prompt: str, user_prompt: str) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 180):
        super().__init__(model or os.getenv("DPER_OPENAI_MODEL", "gpt-5.6-luna"))
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise ProviderError("OpenAI API key is required. Set OPENAI_API_KEY or pass --api-key.")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "text": {"format": {"type": "json_object"}},
        }
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ProviderError(f"OpenAI request failed ({response.status_code}): {response.text[:1000]}")
        data = response.json()
        if data.get("output_text"):
            return data["output_text"]
        parts: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    parts.append(content["text"])
        if not parts:
            raise ProviderError("OpenAI response did not contain output text.")
        return "".join(parts)


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 180):
        super().__init__(model or os.getenv("DPER_CLAUDE_MODEL", "claude-sonnet-4-5"))
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise ProviderError("Claude API key is required. Set ANTHROPIC_API_KEY or pass --api-key.")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": 8192,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Claude request failed ({response.status_code}): {response.text[:1000]}")
        data = response.json()
        parts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
        if not parts:
            raise ProviderError("Claude response did not contain text content.")
        return "".join(parts)


class LocalGGUFProvider(LLMProvider):
    def __init__(self, model_path: str | Path, model: str | None = None, n_ctx: int = 8192):
        super().__init__(model or str(model_path))
        try:
            from llama_cpp import Llama
        except Exception as exc:  # pragma: no cover - optional dependency
            raise ProviderError("Local GGUF mode requires llama-cpp-python. Install with: pip install .[local]") from exc
        path = Path(model_path)
        if not path.exists():
            raise ProviderError(f"Local model file not found: {path}")
        self.llm = Llama(model_path=str(path), n_ctx=n_ctx, verbose=False)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{user_prompt}\n<|assistant|>\n"
        result = self.llm(prompt, max_tokens=4096, temperature=0.0, stop=["<|user|>", "<|system|>"])
        return result["choices"][0]["text"]


class DryRunProvider(LLMProvider):
    def __init__(self):
        super().__init__("dry-run")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "dog": {"dog_name": "Unknown", "species": "canine", "evidence_quote": "dry-run"},
                "visits": [],
                "new_candidate_phenotypes": [],
            }
        )


def make_provider(provider: str, api_key: str | None = None, model: str | None = None, local_model: str | None = None) -> LLMProvider:
    provider = provider.lower().strip()
    if provider == "openai":
        return OpenAIProvider(api_key=api_key, model=model)
    if provider in {"claude", "anthropic"}:
        return ClaudeProvider(api_key=api_key, model=model)
    if provider in {"local", "gguf", "llama"}:
        if not local_model:
            raise ProviderError("Local provider requires --local-model pointing to a .gguf file.")
        return LocalGGUFProvider(local_model, model=model)
    if provider == "dry-run":
        return DryRunProvider()
    raise ProviderError(f"Unknown provider: {provider}")
