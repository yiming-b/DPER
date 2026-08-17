import {
  buildDatasetColumns,
  DEFAULT_PHENOTYPES,
  formatDateList,
  normalizeColor,
  normalizeReproductiveStatus,
  normalizeSex,
  normalizeSpecies,
  normalizeWeight,
  normalizeWhitespace,
  slug,
  standardizeDate,
  uniqueDates,
} from "../../phenotypes";
import type { PhenotypeDefinition } from "../../phenotypes";

type Provider = "openai" | "claude";

type ReportPayload = {
  fileName: string;
  text: string;
};

type PhenotypePayload = string | {
  id?: unknown;
  label?: unknown;
};

function parseJsonObject(raw: string) {
  const trimmed = raw.trim().replace(/^```(?:json)?/i, "").replace(/```$/, "").trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");
    if (start < 0 || end <= start) throw new Error("Model did not return JSON.");
    return JSON.parse(trimmed.slice(start, end + 1));
  }
}

function phenotypesFromPayload(input: unknown): PhenotypeDefinition[] {
  if (!Array.isArray(input)) return DEFAULT_PHENOTYPES;

  const seen = new Set<string>();
  const phenotypes: PhenotypeDefinition[] = [];
  for (const item of input) {
    let rawLabel = "";
    let rawId = "";
    if (typeof item === "string") {
      rawLabel = item;
      rawId = item;
    } else if (typeof item === "object" && item) {
      const phenotype = item as Exclude<PhenotypePayload, string>;
      rawLabel = typeof phenotype.label === "string" ? phenotype.label : "";
      rawId = typeof phenotype.id === "string" ? phenotype.id : rawLabel;
      if (!rawLabel) rawLabel = rawId;
    }
    const id = slug(rawId);
    const label = normalizeWhitespace(rawLabel || rawId);
    if (!id || !label || seen.has(id)) continue;
    seen.add(id);
    phenotypes.push({
      id,
      label,
      terms: [label],
    });
  }
  return phenotypes;
}

function buildPrompt(report: ReportPayload, phenotypes: PhenotypeDefinition[], includeIdentityColumns: boolean) {
  const phenotypeList = phenotypes.length
    ? phenotypes
      .map((phenotype) => `- ${phenotype.id}${phenotype.label !== phenotype.id ? `: ${phenotype.label}` : ""}`)
      .join("\n")
    : "No phenotype columns requested.";
  const examplePhenotype = phenotypes[0]?.id || "phenotype_column";
  const phenotypeShape = phenotypes.length
    ? `  "phenotypes": {
    "${examplePhenotype}": {
      "present": ["MM/DD/YYYY"]
    }
  }`
    : `  "phenotypes": {}`;
  const identityShape = includeIdentityColumns
    ? `  "patient_id": "",
  "dog_name": "",
  "species": "canine",
  "breed_raw": "",
  "sex": "",
  "reproductive_status": "",
  "color": "",
  "weight": "",
  "date_of_birth": "",
  "age_reported": "",
  "visit_dates": ["MM/DD/YYYY"],`
    : "";
  const identityRule = includeIdentityColumns
    ? "- Extract dog identity and demographic fields only; do not extract owner/client/contact fields."
    : "- Do not extract dog identity or demographic fields unless needed to understand a requested phenotype.";

  return `Extract dog phenotype information from this veterinary PDF text.

Create exactly one table row for this source file. The file may contain multiple visits for the same dog; keep those visits inside dated values instead of creating multiple rows.

Use only these exact phenotype columns:
${phenotypeList}

Return JSON only with this shape:
{
${identityShape}
${phenotypeShape}
}

Rules:
- Do not extract or return owner, client, address, phone, or email information.
${identityRule}
- Standardize every date as MM/DD/YYYY. If a date cannot be determined, use an empty string.
- Standardize color as lower-case terms separated by comma, for example "black, white".
- For stable demographic fields, return a string. If a demographic field has conflicting values across visits, return an object mapping each normalized value to its visit date or date array. Example: {"grey":"11/01/2009","black, white":"06/30/2011"}.
- Phenotype values must be objects mapping one of present, absent, suspected, rule_out, historical, resolved, normal, abnormal to a visit date or date array. Use an empty string only when the phenotype is not mentioned.
- The keys inside "phenotypes" must exactly match the requested phenotype column ids.
- Do not infer normal findings from silence.

SOURCE FILE: ${report.fileName}

PDF TEXT:
${report.text.slice(0, 60000)}`;
}

async function callOpenAI(apiKey: string, model: string, prompt: string) {
  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: model || "gpt-5.6-luna",
      instructions: "You extract canine phenotype datasets. Return JSON only.",
      input: prompt,
      text: { format: { type: "json_object" } },
    }),
  });
  const data = await response.json() as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(typeof data.error === "object" ? JSON.stringify(data.error) : "OpenAI request failed.");
  }
  if (typeof data.output_text === "string") return data.output_text;
  const output = Array.isArray(data.output) ? data.output : [];
  const parts: string[] = [];
  for (const item of output) {
    const content = typeof item === "object" && item && "content" in item ? (item as { content?: unknown }).content : undefined;
    if (!Array.isArray(content)) continue;
    for (const block of content) {
      if (typeof block === "object" && block && "text" in block && typeof (block as { text?: unknown }).text === "string") {
        parts.push((block as { text: string }).text);
      }
    }
  }
  return parts.join("");
}

async function callClaude(apiKey: string, model: string, prompt: string) {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: model || "claude-sonnet-4-5",
      max_tokens: 4096,
      system: "You extract canine phenotype datasets. Return JSON only.",
      messages: [{ role: "user", content: prompt }],
    }),
  });
  const data = await response.json() as { content?: Array<{ type: string; text?: string }>; error?: unknown };
  if (!response.ok) throw new Error(data.error ? JSON.stringify(data.error) : "Claude request failed.");
  return (data.content || []).filter((block) => block.type === "text").map((block) => block.text || "").join("");
}

function normalizeDateValue(value: unknown): unknown {
  if (typeof value === "string") return standardizeDate(value) || normalizeWhitespace(value);
  if (Array.isArray(value)) {
    const dates = uniqueDates(value.map((item) => typeof item === "string" ? standardizeDate(item) : "").filter(Boolean));
    return dates.length > 1 ? dates : dates[0] || "";
  }
  return value;
}

function stringifyCellValue(value: unknown, normalizeKey?: (key: string) => string, normalizeScalar?: (value: string) => string) {
  if (typeof value === "string") return normalizeScalar ? normalizeScalar(value) : normalizeWhitespace(value);
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) {
    const dates = value.map((item) => typeof item === "string" ? standardizeDate(item) : "").filter(Boolean);
    return dates.length ? formatDateList(dates) : JSON.stringify(value);
  }
  if (typeof value === "object" && value) {
    const output: Record<string, unknown> = {};
    for (const [rawKey, rawValue] of Object.entries(value)) {
      const key = normalizeKey ? normalizeKey(rawKey) : normalizeWhitespace(rawKey);
      if (!key) continue;
      output[key] = normalizeDateValue(rawValue);
    }
    return Object.keys(output).length ? JSON.stringify(output) : "";
  }
  return "";
}

function modelField(extracted: Record<string, unknown>, field: string, normalizeScalar?: (value: string) => string, normalizeKey?: (key: string) => string) {
  return stringifyCellValue(extracted[field], normalizeKey, normalizeScalar);
}

function modelPhenotypeCell(value: unknown) {
  if (typeof value === "string") return normalizeWhitespace(value);
  if (typeof value === "object" && value) return stringifyCellValue(value, (key) => normalizeWhitespace(key).toLowerCase());
  return "";
}

function rowFromModel(index: number, report: ReportPayload, extracted: Record<string, unknown>, phenotypes: PhenotypeDefinition[]) {
  const extractedPhenotypes = typeof extracted.phenotypes === "object" && extracted.phenotypes ? extracted.phenotypes as Record<string, unknown> : {};
  const dogName = typeof extracted.dog_name === "string" && extracted.dog_name ? extracted.dog_name : report.fileName.replace(/\.[^.]+$/, "");
  const row: Record<string, string> = {
    dog_id: `${index + 1}_${slug(dogName, "dog")}`,
    source_file: report.fileName,
    dog_name: dogName,
    patient_id: modelField(extracted, "patient_id"),
    species: modelField(extracted, "species", normalizeSpecies) || "canine",
    breed_raw: modelField(extracted, "breed_raw"),
    sex: modelField(extracted, "sex", normalizeSex),
    reproductive_status: modelField(extracted, "reproductive_status", normalizeReproductiveStatus),
    color: modelField(extracted, "color", normalizeColor, normalizeColor),
    weight: modelField(extracted, "weight", normalizeWeight, normalizeWeight),
    date_of_birth: modelField(extracted, "date_of_birth", (value) => standardizeDate(value) || normalizeWhitespace(value)),
    age_reported: modelField(extracted, "age_reported", (value) => normalizeWhitespace(value).toLowerCase()),
    visit_dates: modelField(extracted, "visit_dates", (value) => standardizeDate(value) || normalizeWhitespace(value)),
    phenotype_event_count: "0",
  };
  let count = 0;
  for (const phenotype of phenotypes) {
    const value = modelPhenotypeCell(extractedPhenotypes[phenotype.id]);
    row[phenotype.id] = value;
    if (value) count += 1;
  }
  row.phenotype_event_count = String(count);
  return row;
}

export async function POST(request: Request) {
  try {
    const payload = await request.json() as {
      provider?: Provider;
      apiKey?: string;
      model?: string;
      includeIdentityColumns?: boolean;
      phenotypes?: unknown;
      reports?: ReportPayload[];
    };
    if (!payload.apiKey) return Response.json({ error: "API key is required." }, { status: 400 });
    const reports = payload.reports || [];
    if (!reports.length) return Response.json({ error: "At least one report is required." }, { status: 400 });

    const provider = payload.provider === "claude" ? "claude" : "openai";
    const includeIdentityColumns = payload.includeIdentityColumns !== false;
    const phenotypes = phenotypesFromPayload(payload.phenotypes);
    const rows = [];
    for (let index = 0; index < reports.length; index += 1) {
      const prompt = buildPrompt(reports[index], phenotypes, includeIdentityColumns);
      const raw = provider === "claude"
        ? await callClaude(payload.apiKey, payload.model || "", prompt)
        : await callOpenAI(payload.apiKey, payload.model || "", prompt);
      rows.push(rowFromModel(index, reports[index], parseJsonObject(raw), phenotypes));
    }
    return Response.json({ columns: buildDatasetColumns(includeIdentityColumns, phenotypes), rows });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Extraction failed.";
    return Response.json({ error: message }, { status: 500 });
  }
}
