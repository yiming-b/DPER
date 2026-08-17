from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .local_models import QWEN3_4B_MODEL_ID, default_qwen_model_path


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
        super().__init__(model or os.getenv("DPER_CLAUDE_MODEL", "claude-sonnet-5"))
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
    def __init__(
        self,
        model_path: str | Path,
        model: str | None = None,
        n_ctx: int = 16384,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        top_p: float = 0.8,
    ):
        super().__init__(model or str(model_path))
        try:
            from llama_cpp import Llama
        except Exception as exc:  # pragma: no cover - optional dependency
            raise ProviderError('Local GGUF mode requires llama-cpp-python. Install with: python -m pip install -e ".[local]"') from exc
        path = Path(model_path).expanduser()
        if not path.exists():
            raise ProviderError(
                f"Local model file not found: {path}\n"
                "Download the recommended Qwen3 4B model with: dper-download-qwen3"
            )
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.llm = Llama(model_path=str(path), n_ctx=n_ctx, verbose=False)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        qwen_user_prompt = f"{user_prompt}\n\n/no_think\nReturn exactly one JSON object and no Markdown."
        try:
            try:
                result = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": qwen_user_prompt},
                    ],
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    response_format={"type": "json_object"},
                )
            except TypeError:
                result = self.llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": qwen_user_prompt},
                    ],
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                )
            text = result["choices"][0]["message"]["content"]
        except Exception:
            prompt = (
                f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                f"<|im_start|>user\n{qwen_user_prompt}<|im_end|>\n"
                "<|im_start|>assistant\n"
            )
            result = self.llm(
                prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                stop=["<|im_end|>", "<|im_start|>"],
            )
            text = result["choices"][0]["text"]
        return self._strip_reasoning(text)

    def _strip_reasoning(self, text: str) -> str:
        text = re.sub(r"(?is)^\s*<think>.*?</think>", "", text or "").strip()
        return text


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


class DefaultPhenotypeProvider(LLMProvider):
    """Built-in dictionary-guided extractor used when no API key is supplied."""

    def __init__(self):
        super().__init__("default-dictionary-extractor")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        chunk = self._section(user_prompt, "REPORT CHUNK:", "OUTPUT JSON SHAPE:")
        dictionary_rows = self._dictionary_rows(user_prompt)
        source_file = self._metadata(user_prompt, "source_file")
        dog = self._extract_dog(chunk, source_file)
        events = self._extract_events(chunk, dictionary_rows)
        visit = {
            "visit_date": self._first_date(chunk),
            "visit_type": "unknown",
            "visit_reason_raw": "",
            "evidence_quote": chunk[:240],
            "page_number": self._first_page(chunk),
            "confidence": 0.45,
            "vitals": self._extract_vitals(chunk),
            "diet_environment": {},
            "exam_summaries": {},
            "phenotype_events": events,
            "lab_results": [],
            "diagnostic_events": [],
            "medication_events": [],
            "procedure_events": [],
        }
        return json.dumps({"dog": dog, "visits": [visit], "new_candidate_phenotypes": []})

    def _dictionary_rows(self, prompt: str) -> list[dict[str, Any]]:
        start = prompt.find("[")
        end = prompt.find("\n\nSOURCE METADATA:", start)
        if start < 0 or end < 0:
            return []
        try:
            data = json.loads(prompt[start:end].strip())
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _section(self, prompt: str, start_label: str, end_label: str) -> str:
        start = prompt.find(start_label)
        if start < 0:
            return ""
        start += len(start_label)
        end = prompt.find(end_label, start)
        if end < 0:
            end = len(prompt)
        return prompt[start:end].strip()

    def _metadata(self, prompt: str, key: str) -> str:
        m = re.search(rf"(?m)^{re.escape(key)}:\s*(.+)$", prompt)
        return m.group(1).strip() if m else ""

    def _extract_dog(self, text: str, source_file: str = "") -> dict[str, Any]:
        dog: dict[str, Any] = {"species": "canine", "evidence_quote": text[:220]}
        patterns = {
            "dog_name": [
                r"PATIENT INFORMATION\s+Name\s+([A-Z][A-Za-z '\-()]{1,50})\s+Species\b",
                r"\bName\s*:?\s*([A-Z][A-Za-z '\-()]{1,50})\s+Species\b",
                r"\bPet Name\s*:?\s*([A-Z][A-Za-z '\-()]{1,50})\b",
                r"\bPatient\s*:?\s*(?:#?\d+,?\s*)?([A-Z][A-Za-z '\-()]{1,50})(?:\s|\.|,)",
                r"Clinical History for\s+([A-Z][A-Za-z '\-()]{1,50})\b",
            ],
            "breed_raw": [r"\bBreed\s*:?\s*([A-Za-z (),/&.\-]{2,80})", r"\bBreed \(Species\):\s*([^(\n]+)"],
            "sex_raw": [r"\b(?:Sex|Gender)\s*:?\s*(Male\s*/\s*Neutered|Female\s*/\s*Spayed|Male,\s*Neutered|Female,\s*Spayed|Male Neutered|Female Spayed|MN|FS|Male|Female)"],
            "date_of_birth": [r"\b(?:DOB|D\.O\.B\.|Birthday|Birthdate)\s*:?\s*([0-9A-Za-z/\-.]+)"],
            "age_reported": [r"\bAge\s*:?\s*([0-9A-Za-z .]+)"],
            "coat_color": [r"\b(?:Color|Coat Color|Colour)\s*:?\s*([A-Za-z/& \-]+)"],
        }
        for key, pats in patterns.items():
            for pat in pats:
                m = re.search(pat, text, re.I)
                if m:
                    value = re.sub(r"\s+", " ", m.group(1)).strip(" ,.;")
                    if key == "dog_name" and self._reject_name(value):
                        continue
                    dog[key] = self._clean_demographic_value(key, value)
                    break
        if not dog.get("dog_name") and source_file:
            dog["dog_name"] = Path(source_file).stem.split("_")[0].split("-")[0].strip() or None
        sex_raw = dog.get("sex_raw", "").lower()
        if "female" in sex_raw or sex_raw == "fs":
            dog["sex"] = "female"
        elif "male" in sex_raw or sex_raw == "mn":
            dog["sex"] = "male"
        if "spay" in sex_raw or sex_raw == "fs":
            dog["reproductive_status"] = "spayed"
        elif "neuter" in sex_raw or sex_raw == "mn":
            dog["reproductive_status"] = "neutered"
        return dog

    def _reject_name(self, value: str) -> bool:
        return value.lower().strip() in {
            "chart",
            "patient",
            "patient information",
            "client",
            "client information",
            "owner",
            "medical history",
        }

    def _clean_demographic_value(self, key: str, value: str) -> str:
        split_terms = {
            "breed_raw": [" Age", " Sex", " Weight", " Color", " Address", " Home", " DOB", " D.O.B."],
            "coat_color": [" Weight", " Tag", " Microchip", " Rabies", " DOB", " Age", " Sex"],
            "age_reported": [" ID", " Color", " Sex", " Weight"],
        }.get(key, [])
        for term in split_terms:
            idx = value.lower().find(term.lower())
            if idx > 0:
                value = value[:idx]
        return value.strip(" ,.;")

    def _extract_vitals(self, text: str) -> dict[str, Any]:
        vitals: dict[str, Any] = {}
        patterns = {
            "weight_lb": r"\b(?:Weight|WT LB|Wt)\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:lb|lbs|pounds|#)\b",
            "weight_kg": r"\b(?:Weight|WT KG|Wt)\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*kg\b",
            "temperature_f": r"\b(?:Temp|Temperature)\s*:?\s*([0-9]{2,3}(?:\.[0-9]+)?)",
            "heart_rate_bpm": r"\b(?:Heart Rate|HR|Pulse)\s*:?\s*([0-9]{2,3})\b",
            "respiratory_rate_bpm": r"\b(?:Respiration|Respiratory Rate|RR)\s*:?\s*([0-9]{1,3})\b",
            "body_condition_score": r"\b(?:BCS|Body Condition Score)\s*:?\s*([0-9](?:\.[0-9])?)",
        }
        for key, pat in patterns.items():
            m = re.search(pat, text, re.I)
            if m:
                vitals[key] = m.group(1)
        return vitals

    def _extract_events(self, text: str, dictionary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        lowered = text.lower()
        events: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in dictionary_rows:
            if row.get("target_table") != "phenotype_events":
                continue
            phenotype_id = row.get("phenotype_id", "")
            label = row.get("field_or_phenotype", "")
            candidates = [label, phenotype_id.replace("_", " ")]
            examples = str(row.get("examples_observed_in_reports", ""))
            candidates.extend(re.findall(r"[A-Za-z][A-Za-z /-]{3,}", examples))
            match_term = ""
            for candidate in candidates:
                term = candidate.lower().strip(" ,.;")
                if len(term) >= 4 and term in lowered:
                    match_term = candidate
                    break
            if not match_term or phenotype_id in seen:
                continue
            seen.add(phenotype_id)
            events.append(
                {
                    "phenotype_id": phenotype_id,
                    "status": self._status_for(text, match_term),
                    "value_raw": match_term,
                    "value_normalized": phenotype_id,
                    "source_sentence": self._evidence(text, match_term),
                    "page_number": self._first_page(text),
                    "confidence": 0.52,
                    "needs_review": "yes",
                }
            )
        return events

    def _status_for(self, text: str, term: str) -> str:
        idx = text.lower().find(term.lower())
        window = text[max(0, idx - 80) : idx + 120].lower() if idx >= 0 else text[:200].lower()
        if re.search(r"\b(no|not|negative for|none|absent)\b", window):
            return "absent"
        if re.search(r"\br/o|rule out|rule-out|differential", window):
            return "rule_out"
        if re.search(r"\bsuspect|suspected|possible|concern for", window):
            return "suspected"
        if re.search(r"\bhistory of|historical|previous", window):
            return "historical"
        if re.search(r"\bresolved|inactive", window):
            return "resolved"
        return "present"

    def _evidence(self, text: str, term: str) -> str:
        idx = text.lower().find(term.lower())
        if idx < 0:
            return text[:300]
        start = max(text.rfind(".", 0, idx), text.rfind("\n", 0, idx), 0)
        end_candidates = [pos for pos in [text.find(".", idx), text.find("\n", idx)] if pos > idx]
        end = min(end_candidates) if end_candidates else min(len(text), idx + 240)
        return re.sub(r"\s+", " ", text[start:end]).strip(" .")[:400]

    def _first_page(self, text: str) -> int:
        m = re.search(r"=== PAGE (\d+) ===", text)
        return int(m.group(1)) if m else 1

    def _first_date(self, text: str) -> str:
        m = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4}|[A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})\b", text)
        return m.group(1) if m else ""


def make_provider(provider: str, api_key: str | None = None, model: str | None = None, local_model: str | None = None) -> LLMProvider:
    provider = provider.lower().strip()
    if provider in {"default", "builtin", "built-in"}:
        return DefaultPhenotypeProvider()
    if provider == "openai":
        return OpenAIProvider(api_key=api_key, model=model)
    if provider in {"claude", "anthropic"}:
        return ClaudeProvider(api_key=api_key, model=model)
    if provider in {"local-qwen", "qwen", "qwen3", "qwen3-4b"}:
        return LocalGGUFProvider(local_model or default_qwen_model_path(), model=model or QWEN3_4B_MODEL_ID)
    if provider in {"local", "gguf", "llama"}:
        if not local_model:
            raise ProviderError("Local provider requires --local-model pointing to a .gguf file.")
        return LocalGGUFProvider(local_model, model=model)
    if provider == "dry-run":
        return DryRunProvider()
    raise ProviderError(f"Unknown provider: {provider}")
