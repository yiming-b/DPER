"use client";

import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { FileUp, Upload } from "lucide-react";
import {
  buildDatasetColumns,
  DEFAULT_PHENOTYPES,
  findDateHits,
  formatDateList,
  formatDatedStatusValues,
  formatObservedValues,
  IDENTITY_COLUMNS,
  mergePhenotypes,
  nearestDateForIndex,
  normalizeColor,
  normalizeReproductiveStatus,
  normalizeSex,
  normalizeSpecies,
  normalizeWeight,
  normalizeWhitespace,
  parsePhenotypeList,
  slug,
  standardizeDate,
} from "./phenotypes";
import type { PhenotypeDefinition } from "./phenotypes";

type Provider = "openai" | "claude";
type Mode = "default" | "api";
type ReportText = { fileName: string; text: string; pageCount: number };
type DatasetRow = Record<string, string>;

const DEFAULT_OPENAI_MODEL = "gpt-5.6-luna";
const DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5";

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

function toGlobalRegex(pattern: RegExp) {
  return new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`);
}

function cleanFieldValue(value: string) {
  return normalizeWhitespace(value)
    .split(/\b(?:Owner|Client|Address|Phone|Email|Species|Breed|Age|Sex|Gender|Weight|Color|Colour|DOB|Date of Birth)\b/i)[0]
    .replace(/[.,;:]$/, "")
    .trim();
}

function collectFieldObservations(
  text: string,
  patterns: RegExp[],
  dateHits: ReturnType<typeof findDateHits>,
  normalizeValue: (value: string) => string = cleanFieldValue,
) {
  const observations = [];
  const seen = new Set<string>();
  for (const pattern of patterns) {
    const regex = toGlobalRegex(pattern);
    for (const match of text.matchAll(regex)) {
      const rawValue = match[1] || "";
      const value = normalizeValue(cleanFieldValue(rawValue));
      if (!value) continue;
      const date = nearestDateForIndex(dateHits, match.index ?? 0);
      const key = `${value}|${date}`;
      if (seen.has(key)) continue;
      seen.add(key);
      observations.push({ value, date });
    }
  }
  return observations;
}

function collectDateField(text: string, patterns: RegExp[]) {
  const observations = [];
  const seen = new Set<string>();
  for (const pattern of patterns) {
    const regex = toGlobalRegex(pattern);
    for (const match of text.matchAll(regex)) {
      const value = standardizeDate(match[1] || "");
      if (!value || seen.has(value)) continue;
      seen.add(value);
      observations.push({ value });
    }
  }
  return observations;
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

function phenotypeEvents(text: string, dateHits: ReturnType<typeof findDateHits>, phenotype: PhenotypeDefinition) {
  const lower = text.toLowerCase();
  const events = [];
  const seen = new Set<string>();
  for (const term of phenotype.terms) {
    const target = term.toLowerCase();
    let index = lower.indexOf(target);
    while (index >= 0) {
      const status = inferStatus(text, term);
      const date = nearestDateForIndex(dateHits, index);
      const key = `${status}|${date}`;
      if (!seen.has(key)) {
        seen.add(key);
        events.push({ value: status, date });
      }
      index = lower.indexOf(target, index + target.length);
    }
  }
  return events;
}

function defaultExtract(reports: ReportText[], phenotypes: PhenotypeDefinition[], includeIdentityColumns: boolean) {
  const rows = reports.map((report, index) => {
    const text = report.text;
    const dateHits = findDateHits(text);
    const dogName =
      extractField(text, [
        /\bName\s*:?\s*([A-Za-z][A-Za-z '\-()]{1,50})\s+Species\b/i,
        /\bPatient\s*:?\s*(?:#?\d+,?\s*)?([A-Za-z][A-Za-z '\-()]{1,50})(?:\s|\.|,)/i,
        /Clinical History for\s+([A-Za-z][A-Za-z '\-()]{1,50})\b/i,
      ]) || report.fileName.replace(/\.[^.]+$/, "").split(/[_-]/)[0];
    const species = collectFieldObservations(text, [/\bSpecies\s*:?\s*([A-Za-z ]{3,30})/i], dateHits, normalizeSpecies);
    const breed = collectFieldObservations(text, [/\bBreed\s*:?\s*([^.\n\r]{2,90})/i, /\bBreed \(Species\):\s*([^(\n\r]+)/i], dateHits);
    const sex = collectFieldObservations(text, [/\b(?:Sex|Gender)\s*:?\s*(Male\s*\/\s*Neutered|Female\s*\/\s*Spayed|Male,\s*Neutered|Female,\s*Spayed|Neutered Male|Spayed Female|Intact Male|Intact Female|MN|FS|M\/N|F\/S|Male|Female)/i], dateHits, normalizeSex);
    const reproductiveStatus = collectFieldObservations(text, [/\b(?:Sex|Gender|Reproductive Status|Status)\s*:?\s*(Male\s*\/\s*Neutered|Female\s*\/\s*Spayed|Male,\s*Neutered|Female,\s*Spayed|Neutered Male|Spayed Female|Intact Male|Intact Female|Spayed|Neutered|Intact|MN|FS|M\/N|F\/S)/i], dateHits, normalizeReproductiveStatus);
    const color = collectFieldObservations(text, [/\b(?:Color|Colour|Coat Color|Coat Colour)\s*:?\s*([^.\n\r]{2,80})/i], dateHits, normalizeColor);
    const weight = collectFieldObservations(text, [/\b(?:Weight|Wt)\s*:?\s*([0-9]+(?:\.[0-9]+)?\s*(?:kg|kgs|kilograms?|lb|lbs|pounds?)?)/i], dateHits, normalizeWeight);
    const age = collectFieldObservations(text, [/\bAge\s*:?\s*([^.\n\r]{1,60})/i], dateHits, (value) => normalizeWhitespace(value).toLowerCase());
    const dob = collectDateField(text, [/\b(?:DOB|D\.O\.B\.|Birthday|Birthdate|Date of Birth)\s*:?\s*([0-9A-Za-z/\-., ]{6,24})/i]);
    const patientId = extractField(text, [
      /\b(?:Patient|Pet|Animal)\s*(?:ID|#)\s*:?\s*([A-Za-z0-9-]{2,40})/i,
      /\b(?:Patient|Pet|Animal)\s+Number\s*:?\s*([A-Za-z0-9-]{2,40})/i,
    ]);
    const row: DatasetRow = {
      dog_id: `${index + 1}_${slug(dogName, "dog")}`,
      source_file: report.fileName,
      dog_name: dogName,
      patient_id: patientId,
      species: formatObservedValues(species) || "canine",
      breed_raw: formatObservedValues(breed),
      sex: formatObservedValues(sex),
      reproductive_status: formatObservedValues(reproductiveStatus),
      color: formatObservedValues(color),
      weight: formatObservedValues(weight),
      date_of_birth: formatObservedValues(dob),
      age_reported: formatObservedValues(age),
      visit_dates: formatDateList(dateHits.map((hit) => hit.value)),
      phenotype_event_count: "0",
    };
    let eventCount = 0;
    for (const phenotype of phenotypes) {
      const events = phenotypeEvents(text, dateHits, phenotype);
      row[phenotype.id] = formatDatedStatusValues(events);
      if (events.length) eventCount += 1;
    }
    row.phenotype_event_count = String(eventCount);
    return row;
  });
  return { columns: buildDatasetColumns(includeIdentityColumns, phenotypes), rows };
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
  const [phenotypeText, setPhenotypeText] = useState("");
  const [includeIdentityColumns, setIncludeIdentityColumns] = useState(true);
  const [includeDefaultPhenotypes, setIncludeDefaultPhenotypes] = useState(true);
  const [files, setFiles] = useState<FileList | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<DatasetRow[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  const visibleColumns = useMemo(() => columns.slice(0, 18), [columns]);
  const customPhenotypes = useMemo(() => parsePhenotypeList(phenotypeText), [phenotypeText]);
  const extractionPhenotypes = useMemo(
    () => mergePhenotypes(customPhenotypes, includeDefaultPhenotypes),
    [customPhenotypes, includeDefaultPhenotypes],
  );
  const customPhenotypeIds = useMemo(() => new Set(customPhenotypes.map((phenotype) => phenotype.id)), [customPhenotypes]);
  const defaultPhenotypesInOutput = includeDefaultPhenotypes
    ? DEFAULT_PHENOTYPES.filter((phenotype) => !customPhenotypeIds.has(phenotype.id))
    : [];
  const removedDuplicateDefaults = includeDefaultPhenotypes ? DEFAULT_PHENOTYPES.length - defaultPhenotypesInOutput.length : 0;
  const isCustomPhenotypeList = customPhenotypes.length > 0;
  const canDownload = rows.length > 0 && columns.length > 0;
  const phenotypeStep = mode === "api" ? "3" : "2";
  const fileStep = mode === "api" ? "4" : "3";

  async function handlePhenotypeFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      setError("");
      setPhenotypeText(await file.text());
    } catch {
      setError("Could not read the phenotype .txt file.");
    }
  }

  async function runExtraction() {
    setError("");
    setStatus("");
    setRows([]);
    setColumns([]);
    if (!files?.length) {
      setError("Select at least one PDF report.");
      return;
    }
    if (phenotypeText.trim() && !customPhenotypes.length) {
      setError("Enter at least one phenotype, separated by line or comma, or clear the custom list to use the default.");
      return;
    }
    if (!includeIdentityColumns && !extractionPhenotypes.length) {
      setError("Select identity fields, default phenotypes, or enter a custom phenotype list.");
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
        const dataset = defaultExtract(reportTexts, extractionPhenotypes, includeIdentityColumns);
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
            includeIdentityColumns,
            phenotypes: extractionPhenotypes.map((phenotype) => ({ id: phenotype.id, label: phenotype.label })),
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
          <p>Upload dog veterinary PDFs, extract identity, demographics, dated phenotype fields, and download dataset.csv.</p>
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
                <span><strong>Default Extractor</strong><small>Built-in dictionary extraction with dated phenotype cells</small></span>
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
            <legend>{phenotypeStep}. Output Columns</legend>
            <p className="helper-text">
              Custom phenotype lists are for disease, procedure, behavior, or finding columns. Identity and demographic fields are controlled separately.
            </p>
            <div className="checkbox-grid">
              <label className="check-card" aria-label="Default Identity Fields">
                <input
                  type="checkbox"
                  checked={includeIdentityColumns}
                  onChange={(event) => setIncludeIdentityColumns(event.target.checked)}
                />
                <span><strong>Default Identity Fields</strong><small>Dog identity, species, breed, sex, color, weight, age, visit dates</small></span>
              </label>
              <label className="check-card" aria-label="Default Phenotype List">
                <input
                  type="checkbox"
                  checked={includeDefaultPhenotypes}
                  onChange={(event) => setIncludeDefaultPhenotypes(event.target.checked)}
                />
                <span><strong>Default Phenotype List</strong><small>Built-in phenotype columns appended after custom columns</small></span>
              </label>
            </div>
            <label className="field">
              <span>Custom phenotype list</span>
              <textarea
                value={phenotypeText}
                onChange={(event) => setPhenotypeText(event.target.value)}
                placeholder={"vomiting\nheart murmur\nskin mass, weight loss"}
              />
            </label>
            <div className="inline-controls">
              <label className="icon-upload">
                <FileUp aria-hidden="true" size={17} strokeWidth={2.2} />
                <span>Import .txt</span>
                <input className="hidden-file-input" type="file" accept=".txt,text/plain" onChange={handlePhenotypeFileChange} />
              </label>
              {isCustomPhenotypeList && (
                <button type="button" className="text-action" onClick={() => setPhenotypeText("")}>Use default list</button>
              )}
            </div>
            <p className="helper-text">
              Using {customPhenotypes.length} custom phenotype columns and {defaultPhenotypesInOutput.length} default phenotype columns.
              {removedDuplicateDefaults > 0 ? ` Removed ${removedDuplicateDefaults} duplicate default column${removedDuplicateDefaults === 1 ? "" : "s"}.` : ""}
            </p>
            <details className="default-phenotypes" open>
              <summary>Default identity fields ({IDENTITY_COLUMNS.length})</summary>
              <div className="chip-list">
                {IDENTITY_COLUMNS.map((column) => <span key={column}>{column}</span>)}
              </div>
            </details>
            <details className="default-phenotypes">
              <summary>Default phenotype list ({DEFAULT_PHENOTYPES.length})</summary>
              <div className="chip-list">
                {DEFAULT_PHENOTYPES.map((phenotype) => <span key={phenotype.id}>{phenotype.id}</span>)}
              </div>
            </details>
            <details className="default-phenotypes">
              <summary>Final phenotype columns ({extractionPhenotypes.length})</summary>
              <div className="chip-list">
                {extractionPhenotypes.length
                  ? extractionPhenotypes.map((phenotype) => <span key={phenotype.id}>{phenotype.id}</span>)
                  : <span>none selected</span>}
              </div>
            </details>
          </fieldset>

          <fieldset>
            <legend>{fileStep}. Dog PDF Files</legend>
            <p className="helper-text">
              Each PDF becomes one row. If a PDF contains multiple visits for the same dog, visit dates are kept inside phenotype cells and changed demographic values.
            </p>
            <label className="file-box">
              <input className="hidden-file-input" type="file" accept="application/pdf,.pdf" multiple onChange={(event) => setFiles(event.target.files)} />
              <span className="file-button"><Upload aria-hidden="true" size={19} strokeWidth={2.4} />Choose PDF files</span>
              <span className="file-summary">{files?.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "No PDFs selected"}</span>
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
          <div className="metric"><span>Phenotypes</span><strong>{extractionPhenotypes.length}</strong></div>
          <div className="metric"><span>Identity fields</span><strong>{includeIdentityColumns ? IDENTITY_COLUMNS.length : 0}</strong></div>
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
