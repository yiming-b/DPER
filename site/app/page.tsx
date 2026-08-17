"use client";

import { useMemo, useState } from "react";

type Provider = "openai" | "claude";
type Mode = "default" | "api";
type ReportText = { fileName: string; text: string; pageCount: number };
type DatasetRow = Record<string, string>;

const DEFAULT_OPENAI_MODEL = "gpt-5.6-luna";
const DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5";

const PHENOTYPES = [
  { id: "diarrhea", terms: ["diarrhea", "loose stool", "soft stool"] },
  { id: "vomiting", terms: ["vomiting", "vomited", "vomit"] },
  { id: "decreased_appetite_anorexia", terms: ["decreased appetite", "not eating", "anorexia", "inappetence"] },
  { id: "lethargy", terms: ["lethargy", "lethargic"] },
  { id: "cough", terms: ["cough", "coughing"] },
  { id: "sneezing", terms: ["sneezing", "sneeze"] },
  { id: "pruritus_itching", terms: ["pruritus", "itching", "itchy"] },
  { id: "alopecia", terms: ["alopecia", "hair loss"] },
  { id: "otitis", terms: ["otitis", "ear infection"] },
  { id: "skin_mass_lump", terms: ["mass", "lump", "skin mass"] },
  { id: "lameness_limping", terms: ["lameness", "limping", "limp"] },
  { id: "pain", terms: ["painful", "pain"] },
  { id: "weight_loss", terms: ["weight loss", "losing weight"] },
  { id: "underweight", terms: ["underweight", "thin body condition"] },
  { id: "overweight_obesity", terms: ["overweight", "obese", "obesity"] },
  { id: "heart_murmur", terms: ["heart murmur", "murmur"] },
  { id: "dental_disease", terms: ["dental disease", "tartar", "gingivitis"] },
  { id: "urinary_tract_infection", terms: ["urinary tract infection", "uti"] },
  { id: "proteinuria", terms: ["proteinuria", "protein in urine"] },
  { id: "anxiety_nervousness", terms: ["anxiety", "nervous", "fearful"] },
  { id: "wound_laceration_ulcer", terms: ["wound", "laceration", "ulcer"] },
  { id: "allergic_dermatitis", terms: ["allergic dermatitis", "atopy", "allergy"] },
  { id: "pyoderma", terms: ["pyoderma"] },
  { id: "pancreatitis", terms: ["pancreatitis"] },
  { id: "giardia", terms: ["giardia"] },
  { id: "roundworm_infection", terms: ["roundworm"] },
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

function normalizeWhitespace(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "dog";
}

function csvEscape(value: string) {
  const text = value ?? "";
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function rowsToCsv(columns: string[], rows: DatasetRow[]) {
  const lines = [columns.map(csvEscape).join(",")];
  for (const row of rows) {
    lines.push(columns.map((column) => csvEscape(row[column] || "")).join(","));
  }
  return lines.join("\r\n");
}

function downloadCsv(columns: string[], rows: DatasetRow[]) {
  const blob = new Blob([rowsToCsv(columns, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "dataset.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function extractField(text: string, patterns: RegExp[]) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return normalizeWhitespace(match[1]).replace(/[.,;:]$/, "");
  }
  return "";
}

function inferStatus(text: string, term: string) {
  const lower = text.toLowerCase();
  const index = lower.indexOf(term.toLowerCase());
  const window = index >= 0 ? lower.slice(Math.max(0, index - 90), index + 140) : "";
  if (/\b(no|not|negative for|none|absent|free of)\b/.test(window)) return "absent";
  if (/\b(rule out|rule-out|r\/o|differential)\b/.test(window)) return "rule_out";
  if (/\b(suspect|suspected|possible|concern for)\b/.test(window)) return "suspected";
  if (/\b(history of|historical|previous)\b/.test(window)) return "historical";
  if (/\b(resolved|inactive)\b/.test(window)) return "resolved";
  return "present";
}

function defaultExtract(reports: ReportText[]) {
  const rows = reports.map((report, index) => {
    const text = report.text;
    const dogName =
      extractField(text, [
        /\bName\s*:?\s*([A-Za-z][A-Za-z '\-()]{1,50})\s+Species\b/i,
        /\bPatient\s*:?\s*(?:#?\d+,?\s*)?([A-Za-z][A-Za-z '\-()]{1,50})(?:\s|\.|,)/i,
        /Clinical History for\s+([A-Za-z][A-Za-z '\-()]{1,50})\b/i,
      ]) || report.fileName.replace(/\.[^.]+$/, "").split(/[_-]/)[0];
    const breed = extractField(text, [/\bBreed\s*:?\s*([A-Za-z (),/&.-]{2,80})/i, /\bBreed \(Species\):\s*([^(\n]+)/i]);
    const sexRaw = extractField(text, [/\b(?:Sex|Gender)\s*:?\s*(Male\s*\/\s*Neutered|Female\s*\/\s*Spayed|Male,\s*Neutered|Female,\s*Spayed|MN|FS|Male|Female)/i]);
    const sexLower = sexRaw.toLowerCase();
    const row: DatasetRow = {
      dog_id: `${index + 1}_${slug(dogName)}`,
      source_file: report.fileName,
      dog_name: dogName,
      species: "canine",
      breed_raw: breed.split(/\b(?:Age|Sex|Weight|Color|DOB|Address)\b/i)[0].trim(),
      sex: sexLower.includes("female") || sexLower === "fs" ? "female" : sexLower.includes("male") || sexLower === "mn" ? "male" : "",
      reproductive_status: sexLower.includes("spay") || sexLower === "fs" ? "spayed" : sexLower.includes("neuter") || sexLower === "mn" ? "neutered" : "",
      date_of_birth: extractField(text, [/\b(?:DOB|D\.O\.B\.|Birthday|Birthdate)\s*:?\s*([0-9A-Za-z/\-.]+)/i]),
      age_reported: extractField(text, [/\bAge\s*:?\s*([0-9A-Za-z .]+)/i]).split(/\b(?:ID|Color|Weight|Sex)\b/i)[0].trim(),
      phenotype_event_count: "0",
    };
    let eventCount = 0;
    for (const phenotype of PHENOTYPES) {
      const matchedTerm = phenotype.terms.find((term) => text.toLowerCase().includes(term.toLowerCase()));
      row[phenotype.id] = matchedTerm ? inferStatus(text, matchedTerm) : "";
      if (matchedTerm) eventCount += 1;
    }
    row.phenotype_event_count = String(eventCount);
    return row;
  });
  return { columns: [...BASE_COLUMNS, ...PHENOTYPES.map((phenotype) => phenotype.id)], rows };
}

async function extractPdfText(file: File): Promise<ReportText> {
  const pdfjs = await import("pdfjs-dist");
  pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;
  const data = new Uint8Array(await file.arrayBuffer());
  const pdf = await pdfjs.getDocument({ data }).promise;
  const pages: string[] = [];
  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const content = await page.getTextContent();
    const strings = content.items.map((item) => ("str" in item ? item.str : "")).filter(Boolean);
    pages.push(`=== PAGE ${pageNumber} ===\n${strings.join(" ")}`);
  }
  return { fileName: file.name, text: pages.join("\n\n"), pageCount: pdf.numPages };
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("default");
  const [provider, setProvider] = useState<Provider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [files, setFiles] = useState<FileList | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<DatasetRow[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  const visibleColumns = useMemo(() => columns.slice(0, 18), [columns]);
  const canDownload = rows.length > 0 && columns.length > 0;

  async function runExtraction() {
    setError("");
    setStatus("");
    setRows([]);
    setColumns([]);
    if (!files?.length) {
      setError("Select at least one PDF report.");
      return;
    }
    if (mode === "api" && !apiKey.trim()) {
      setError("Enter an API key or choose the default extractor.");
      return;
    }
    setIsRunning(true);
    try {
      setStatus("Reading PDF text in your browser...");
      const reportTexts = await Promise.all(Array.from(files).map((file) => extractPdfText(file)));
      if (mode === "default") {
        setStatus("Generating dataset.csv with the built-in extractor...");
        const dataset = defaultExtract(reportTexts);
        setColumns(dataset.columns);
        setRows(dataset.rows);
      } else {
        setStatus(`Running ${provider === "openai" ? "OpenAI" : "Claude"} extraction...`);
        const response = await fetch("/api/extract", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider,
            apiKey,
            model: model.trim(),
            reports: reportTexts.map((report) => ({ fileName: report.fileName, text: report.text.slice(0, 60000) })),
          }),
        });
        const payload = await response.json() as { columns?: string[]; rows?: DatasetRow[]; error?: string };
        if (!response.ok) throw new Error(payload.error || "Extraction failed.");
        setColumns(payload.columns || []);
        setRows(payload.rows || []);
      }
      setStatus("dataset.csv is ready.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed.");
      setStatus("");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="page-shell">
      <section className="app-header">
        <div>
          <h1>DPER</h1>
          <p>Upload dog veterinary PDFs, extract phenotype fields, and download dataset.csv.</p>
        </div>
        <span>Browser App</span>
      </section>

      <section className="workspace">
        <div className="control-panel">
          <fieldset>
            <legend>1. Extraction Model</legend>
            <div className="choice-grid">
              <label className="choice-card" htmlFor="mode-default" aria-label="Default Extractor">
                <input id="mode-default" type="radio" name="mode" checked={mode === "default"} onChange={() => setMode("default")} />
                <span><strong>Default Extractor</strong><small>Built-in dictionary extraction, no API key</small></span>
              </label>
              <label className="choice-card" htmlFor="mode-api" aria-label="Plug In LLM">
                <input id="mode-api" type="radio" name="mode" checked={mode === "api"} onChange={() => setMode("api")} />
                <span><strong>Plug In LLM</strong><small>Use your OpenAI or Claude API key</small></span>
              </label>
            </div>
          </fieldset>

          {mode === "api" && (
            <fieldset>
              <legend>2. API Key</legend>
              <div className="segmented">
                <label><input type="radio" name="provider" checked={provider === "openai"} onChange={() => setProvider("openai")} /><span>OpenAI</span></label>
                <label><input type="radio" name="provider" checked={provider === "claude"} onChange={() => setProvider("claude")} /><span>Claude</span></label>
              </div>
              <label className="field">
                <span>API key</span>
                <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Used for this run only" />
              </label>
              <label className="field">
                <span>Model id</span>
                <input type="text" value={model} onChange={(event) => setModel(event.target.value)} placeholder={provider === "openai" ? DEFAULT_OPENAI_MODEL : DEFAULT_CLAUDE_MODEL} />
              </label>
            </fieldset>
          )}

          <fieldset>
            <legend>{mode === "api" ? "3" : "2"}. Dog PDF Files</legend>
            <label className="file-box">
              <input type="file" accept="application/pdf,.pdf" multiple onChange={(event) => setFiles(event.target.files)} />
              <span>{files?.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "Select multiple PDF reports"}</span>
            </label>
          </fieldset>

          <button className="primary-action" onClick={runExtraction} disabled={isRunning}>
            {isRunning ? "Generating..." : "Generate dataset.csv"}
          </button>

          {status && <p className="status-text">{status}</p>}
          {error && <p className="error-text">{error}</p>}
        </div>

        <aside className="summary-panel">
          <h2>Output</h2>
          <div className="metric"><span>Rows</span><strong>{rows.length}</strong></div>
          <div className="metric"><span>Columns</span><strong>{columns.length}</strong></div>
          <div className="metric"><span>Mode</span><strong>{mode === "default" ? "Default" : provider}</strong></div>
          <button className="secondary-action" disabled={!canDownload} onClick={() => downloadCsv(columns, rows)}>Download dataset.csv</button>
        </aside>
      </section>

      {rows.length > 0 && (
        <section className="preview-panel">
          <div className="preview-heading">
            <h2>Preview</h2>
            <p>Showing {Math.min(rows.length, 10)} of {rows.length} rows and {visibleColumns.length} of {columns.length} columns.</p>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr>{visibleColumns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
              <tbody>
                {rows.slice(0, 10).map((row, rowIndex) => (
                  <tr key={rowIndex}>{visibleColumns.map((column) => <td key={column}>{row[column]}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
