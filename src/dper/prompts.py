from __future__ import annotations

import json


SYSTEM_PROMPT = """You extract canine phenotype data from veterinary medical reports.
Return JSON only. Use only facts explicitly supported by the provided report text.
Do not infer normal findings from silence. Do not treat rule-outs as confirmed diagnoses.
Do not infer a diagnosis from medication use unless the source text explicitly links the medication to that diagnosis.
Do not include owner names, owner addresses, phone numbers, or email addresses in extracted tables."""


def build_user_prompt(
    *,
    schema_version: str,
    source_file: str,
    report_id: str,
    chunk_id: str,
    page_start: int,
    page_end: int,
    dictionary_subset: list[dict[str, str]],
    chunk_text: str,
) -> str:
    dictionary_json = json.dumps(dictionary_subset, ensure_ascii=False, indent=2)
    return f"""SCHEMA_VERSION: {schema_version}

TASK:
Extract dog phenotype information from this veterinary report chunk.

CONTROLLED PHENOTYPES:
Use phenotype_id values from these dictionary rows. If an important phenotype is missing, put it in new_candidate_phenotypes instead of inventing an id.
{dictionary_json}

SOURCE METADATA:
source_file: {source_file}
report_id: {report_id}
chunk_id: {chunk_id}
page_start: {page_start}
page_end: {page_end}

REPORT CHUNK:
{chunk_text}

OUTPUT JSON SHAPE:
{{
  "dog": {{
    "dog_name": null,
    "species": null,
    "breed_raw": null,
    "breed_primary": null,
    "mixed_breed_status": null,
    "sex_raw": null,
    "sex": null,
    "reproductive_status": null,
    "date_of_birth": null,
    "age_reported": null,
    "coat_color": null,
    "microchip_id_present": null,
    "rabies_tag_or_id_present": null,
    "source_facility": null,
    "evidence_quote": null
  }},
  "visits": [
    {{
      "visit_date": null,
      "document_date": null,
      "visit_type": null,
      "visit_reason_raw": null,
      "chief_complaint_normalized": null,
      "vitals": {{}},
      "diet_environment": {{}},
      "exam_summaries": {{}},
      "phenotype_events": [
        {{
          "phenotype_id": "diarrhea",
          "status": "present",
          "value_raw": null,
          "value_normalized": null,
          "unit": null,
          "body_site": null,
          "laterality": null,
          "severity": null,
          "duration": null,
          "onset_date": null,
          "resolved_date": null,
          "temporality": null,
          "negation": null,
          "source_sentence": "short evidence quote from this chunk",
          "page_number": {page_start},
          "confidence": 0.0,
          "needs_review": "yes"
        }}
      ],
      "lab_results": [],
      "diagnostic_events": [],
      "medication_events": [],
      "procedure_events": []
    }}
  ],
  "new_candidate_phenotypes": []
}}

OUTPUT RULES:
- Status must be one of: present, absent, suspected, rule_out, historical, resolved, normal, abnormal, not_reported.
- Every non-empty event must include source_sentence, page_number, and confidence.
- Use null or empty arrays for missing data.
- Return exactly one JSON object and no Markdown."""
