# LLM Extraction Prompt Template

Use this as the extraction prompt for one report chunk after text/OCR and page segmentation. Provide the phenotype dictionary rows relevant to the chunk when possible; for small chunks, the full dictionary can be supplied.

## System Message

You extract canine phenotype data from veterinary medical records. Return JSON only. Use only information explicitly supported by the provided text. Do not infer normal findings from silence. Do not treat rule-outs as confirmed diagnoses. Do not infer a diagnosis from medication use unless the source text explicitly links the medication to that diagnosis.

Allowed assertion statuses:

- `present`
- `absent`
- `suspected`
- `rule_out`
- `historical`
- `resolved`
- `normal`
- `abnormal`
- `not_reported`

Every non-empty event must include a concise `evidence_quote`, `page_number`, and `confidence`.

## User Message Template

```text
SCHEMA_VERSION: 0.1.0

TASK:
Extract phenotype information from the veterinary report chunk below.

CONTROLLED PHENOTYPES:
{phenotype_dictionary_subset}

SOURCE METADATA:
source_file: {source_file}
report_id: {report_id}
chunk_id: {chunk_id}
page_start: {page_start}
page_end: {page_end}

REPORT CHUNK:
{chunk_text}

OUTPUT JSON SHAPE:
{
  "dog": {
    "dog_name": null,
    "species": null,
    "breed_raw": null,
    "sex_raw": null,
    "sex": null,
    "reproductive_status": null,
    "date_of_birth": null,
    "age_reported": null,
    "coat_color": null
  },
  "visits": [
    {
      "visit_date": null,
      "visit_type": null,
      "visit_reason_raw": null,
      "vitals": {},
      "diet_environment": {},
      "exam_summaries": {},
      "phenotype_events": [],
      "lab_results": [],
      "diagnostic_events": [],
      "medication_events": [],
      "procedure_events": []
    }
  ],
  "new_candidate_phenotypes": []
}
```

## Output Rules

- Use `null` or empty arrays for missing data.
- For `phenotype_events`, use `phenotype_id` from `schemas/phenotype_dictionary.csv`.
- If a clinically meaningful phenotype is not in the dictionary, put it in `new_candidate_phenotypes` with evidence rather than inventing a new normalized id.
- For labs, preserve `analyte_raw`, `analyte_normalized`, `value`, `unit`, `reference_low`, `reference_high`, `flag`, `specimen`, `collection_date`, `source_panel`, `evidence_quote`, and `page_number`.
- For body-system exams, summarize the system in `exam_summaries` and add phenotype events for specific abnormalities.
- Keep owner phone numbers, addresses, and names out of the phenotype output.
