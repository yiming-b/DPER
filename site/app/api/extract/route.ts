type Provider = "openai" | "claude";

type ReportPayload = {
  fileName: string;
  text: string;
};

const PHENOTYPES = [
  "diarrhea",
  "vomiting",
  "decreased_appetite_anorexia",
  "lethargy",
  "cough",
  "sneezing",
  "pruritus_itching",
  "alopecia",
  "otitis",
  "skin_mass_lump",
  "lameness_limping",
  "pain",
  "weight_loss",
  "underweight",
  "overweight_obesity",
  "heart_murmur",
  "dental_disease",
  "urinary_tract_infection",
  "proteinuria",
  "anxiety_nervousness",
  "wound_laceration_ulcer",
  "allergic_dermatitis",
  "pyoderma",
  "pancreatitis",
  "giardia",
  "roundworm_infection",
];

const BASE_COLUMNS = [
  "dog_id",
  "source_file",
  "dog_name",
  "species",
  "breed_raw",
  "sex",
  "reproductive_status",
  "date_of_birth",
  "age_reported",
  "phenotype_event_count",
];

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "dog";
}

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

function buildPrompt(report: ReportPayload) {
  return `Extract dog phenotype information from this veterinary PDF text.

Use only these phenotype columns:
${PHENOTYPES.join(", ")}

Return JSON only with this shape:
{
  "dog_name": "",
  "species": "canine",
  "breed_raw": "",
  "sex": "",
  "reproductive_status": "",
  "date_of_birth": "",
  "age_reported": "",
  "phenotypes": {
    "diarrhea": "present"
  }
}

Rules:
- Phenotype values must be one of present, absent, suspected, rule_out, historical, resolved, normal, abnormal, or empty string.
- Do not infer normal findings from silence.
- Do not include owner names, addresses, phone numbers, or emails.

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

function rowFromModel(index: number, report: ReportPayload, extracted: Record<string, unknown>) {
  const phenotypes = typeof extracted.phenotypes === "object" && extracted.phenotypes ? extracted.phenotypes as Record<string, unknown> : {};
  const dogName = typeof extracted.dog_name === "string" && extracted.dog_name ? extracted.dog_name : report.fileName.replace(/\.[^.]+$/, "");
  const row: Record<string, string> = {
    dog_id: `${index + 1}_${slug(dogName)}`,
    source_file: report.fileName,
    dog_name: dogName,
    species: typeof extracted.species === "string" ? extracted.species : "canine",
    breed_raw: typeof extracted.breed_raw === "string" ? extracted.breed_raw : "",
    sex: typeof extracted.sex === "string" ? extracted.sex : "",
    reproductive_status: typeof extracted.reproductive_status === "string" ? extracted.reproductive_status : "",
    date_of_birth: typeof extracted.date_of_birth === "string" ? extracted.date_of_birth : "",
    age_reported: typeof extracted.age_reported === "string" ? extracted.age_reported : "",
    phenotype_event_count: "0",
  };
  let count = 0;
  for (const phenotype of PHENOTYPES) {
    const value = typeof phenotypes[phenotype] === "string" ? phenotypes[phenotype] as string : "";
    row[phenotype] = value;
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
      reports?: ReportPayload[];
    };
    if (!payload.apiKey) return Response.json({ error: "API key is required." }, { status: 400 });
    const reports = payload.reports || [];
    if (!reports.length) return Response.json({ error: "At least one report is required." }, { status: 400 });

    const provider = payload.provider === "claude" ? "claude" : "openai";
    const rows = [];
    for (let index = 0; index < reports.length; index += 1) {
      const prompt = buildPrompt(reports[index]);
      const raw = provider === "claude"
        ? await callClaude(payload.apiKey, payload.model || "", prompt)
        : await callOpenAI(payload.apiKey, payload.model || "", prompt);
      rows.push(rowFromModel(index, reports[index], parseJsonObject(raw)));
    }
    return Response.json({ columns: [...BASE_COLUMNS, ...PHENOTYPES], rows });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Extraction failed.";
    return Response.json({ error: message }, { status: 500 });
  }
}
