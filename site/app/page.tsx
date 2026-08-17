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
type DefaultExtractorOption = {
  id: string;
  label: string;
  detail: string;
  availability: string;
};

const MODEL_OPTIONS: Record<Provider, { id: string; label: string }[]> = {
  openai: [
    { id: "gpt-5.6-luna", label: "GPT-5.6 Luna - lower cost" },
    { id: "gpt-5.6-terra", label: "GPT-5.6 Terra - balanced" },
    { id: "gpt-5.6-sol", label: "GPT-5.6 Sol - highest quality" },
  ],
  claude: [
    { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5 - fast" },
    { id: "claude-sonnet-5", label: "Claude Sonnet 5 - balanced" },
    { id: "claude-opus-5", label: "Claude Opus 5 - highest quality" },
  ],
};

const DEFAULT_MODEL_BY_PROVIDER: Record<Provider, string> = {
  openai: "gpt-5.6-luna",
  claude: "claude-sonnet-5",
};

const DEFAULT_EXTRACTOR_OPTIONS: DefaultExtractorOption[] = [
  {
    id: "qwen3-4b-q4km",
    label: "Qwen3 4B Q4_K_M",
    detail: "Recommended local semantic model. Run python .\\scripts\\setup_local_qwen.py once, then use the local DPER website. No OpenAI, Claude, or Hugging Face key is needed for this public Qwen download.",
    availability: "Recommended local",
  },
  {
    id: "regex-dictionary",
    label: "Regex/dictionary extractor",
    detail: "Fallback extractor that runs directly in this browser app. Fast, no API key, no model download.",
    availability: "Available here",
  },
  {
    id: "downloaded-gguf",
    label: "Downloaded GGUF models",
    detail: "The local Python UI detects .gguf files placed in models/. The public hosted page cannot inspect files on a user's computer.",
    availability: "Local backend",
  },
];

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

function defaultExtract(reports: ReportText[], phenotypes: PhenotypeDefinition[], selectedIdentityColumns: string[]) {
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
      const phenotypeCell = formatDatedStatusValues(events);
      row[phenotype.id] = phenotypeCell;
      if (phenotypeCell) eventCount += 1;
    }
    row.phenotype_event_count = String(eventCount);
    return row;
  });
  return { columns: buildDatasetColumns(selectedIdentityColumns, phenotypes), rows };
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
  const [model, setModel] = useState(DEFAULT_MODEL_BY_PROVIDER.openai);
  const [phenotypeText, setPhenotypeText] = useState("");
  const [selectedIdentityColumns, setSelectedIdentityColumns] = useState<string[]>(IDENTITY_COLUMNS);
  const [selectedDefaultPhenotypeIds, setSelectedDefaultPhenotypeIds] = useState<string[]>(DEFAULT_PHENOTYPES.map((phenotype) => phenotype.id));
  const [files, setFiles] = useState<FileList | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<DatasetRow[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  const visibleColumns = useMemo(() => columns.slice(0, 18), [columns]);
  const customPhenotypes = useMemo(() => parsePhenotypeList(phenotypeText), [phenotypeText]);
  const customPhenotypeIds = useMemo(() => new Set(customPhenotypes.map((phenotype) => phenotype.id)), [customPhenotypes]);
  const selectedDefaultPhenotypes = useMemo(
    () => DEFAULT_PHENOTYPES.filter((phenotype) => selectedDefaultPhenotypeIds.includes(phenotype.id)),
    [selectedDefaultPhenotypeIds],
  );
  const defaultPhenotypesInOutput = selectedDefaultPhenotypes.filter((phenotype) => !customPhenotypeIds.has(phenotype.id));
  const extractionPhenotypes = useMemo(
    () => mergePhenotypes(customPhenotypes, selectedDefaultPhenotypes),
    [customPhenotypes, selectedDefaultPhenotypes],
  );
  const removedDuplicateDefaults = selectedDefaultPhenotypes.length - defaultPhenotypesInOutput.length;
  const isCustomPhenotypeList = customPhenotypes.length > 0;
  const canDownload = rows.length > 0 && columns.length > 0;
  const phenotypeStep = "3";
  const fileStep = "4";
  const modelOptions = MODEL_OPTIONS[provider];
  const selectedModel = modelOptions.some((option) => option.id === model) ? model : DEFAULT_MODEL_BY_PROVIDER[provider];

  function handleProviderChange(nextProvider: Provider) {
    setProvider(nextProvider);
    setModel(DEFAULT_MODEL_BY_PROVIDER[nextProvider]);
  }

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

  function toggleIdentityColumn(column: string) {
    setSelectedIdentityColumns((current) => {
      const next = new Set(current);
      if (next.has(column)) next.delete(column);
      else next.add(column);
      return IDENTITY_COLUMNS.filter((identityColumn) => next.has(identityColumn));
    });
  }

  function toggleDefaultPhenotype(phenotypeId: string) {
    setSelectedDefaultPhenotypeIds((current) => {
      const next = new Set(current);
      if (next.has(phenotypeId)) next.delete(phenotypeId);
      else next.add(phenotypeId);
      return DEFAULT_PHENOTYPES.map((phenotype) => phenotype.id).filter((id) => next.has(id));
    });
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
    if (!selectedIdentityColumns.length && !extractionPhenotypes.length) {
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
        const dataset = defaultExtract(reportTexts, extractionPhenotypes, selectedIdentityColumns);
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
            model: selectedModel,
            selectedIdentityColumns,
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
          <h1 aria-label="Dog Phenotype Extractor from Report (DPER)">
            <strong>D</strong>og <strong>P</strong>henotype <strong>E</strong>xtractor from <strong>R</strong>eport <span>(DPER)</span>
          </h1>
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
                <span><strong>Default Extractor</strong><small>Regex-based and local model options</small></span>
              </label>
              <label className="choice-card" htmlFor="mode-api" aria-label="Plug In LLM">
                <input id="mode-api" type="radio" name="mode" checked={mode === "api"} onChange={() => setMode("api")} />
                <span><strong>Plug In LLM</strong><small>Use your OpenAI or Claude API key</small></span>
              </label>
            </div>
          </fieldset>

          {mode === "default" && (
            <fieldset>
              <legend>2. Default / Local Models</legend>
              <div className="model-list">
                {DEFAULT_EXTRACTOR_OPTIONS.map((option) => (
                  <div className={`model-row${option.id === "qwen3-4b-q4km" ? " active" : ""}`} key={option.id}>
                    <span>
                      <strong>{option.label}</strong>
                      <small>{option.detail}</small>
                    </span>
                    <em>{option.availability}</em>
                  </div>
                ))}
              </div>
              <p className="helper-text compact-note">
                This hosted page uses the regex/dictionary extractor for default runs. Downloaded Qwen or other GGUF models run in the local Python website at 127.0.0.1:7860.
              </p>
            </fieldset>
          )}

          {mode === "api" && (
            <fieldset>
              <legend>2. API Key</legend>
              <div className="segmented">
                <label><input type="radio" name="provider" checked={provider === "openai"} onChange={() => handleProviderChange("openai")} /><span>OpenAI</span></label>
                <label><input type="radio" name="provider" checked={provider === "claude"} onChange={() => handleProviderChange("claude")} /><span>Claude</span></label>
              </div>
              <label className="field">
                <span>API key</span>
                <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Used for this run only" />
              </label>
              <label className="field">
                <span>Model</span>
                <select value={selectedModel} onChange={(event) => setModel(event.target.value)}>
                  {modelOptions.map((option) => (
                    <option key={option.id} value={option.id}>{option.label}</option>
                  ))}
                </select>
              </label>
            </fieldset>
          )}

          <fieldset>
            <legend>{phenotypeStep}. Output Columns</legend>
            <p className="helper-text">
              Custom phenotype lists are for disease, procedure, behavior, or finding columns. Identity and demographic fields are controlled separately.
            </p>
            <details className="default-phenotypes" open>
              <summary>Default identity fields ({selectedIdentityColumns.length}/{IDENTITY_COLUMNS.length} selected)</summary>
              <div className="inline-controls compact-actions">
                <button type="button" className="text-action" onClick={() => setSelectedIdentityColumns(IDENTITY_COLUMNS)}>Select all</button>
                <button type="button" className="text-action" onClick={() => setSelectedIdentityColumns([])}>Clear</button>
              </div>
              <div className="option-list">
                {IDENTITY_COLUMNS.map((column) => (
                  <label className="option-check" key={column} aria-label={`Include ${column}`}>
                    <input
                      type="checkbox"
                      checked={selectedIdentityColumns.includes(column)}
                      onChange={() => toggleIdentityColumn(column)}
                    />
                    <span>{column}</span>
                  </label>
                ))}
              </div>
            </details>
            <details className="default-phenotypes" open>
              <summary>Default phenotype list ({defaultPhenotypesInOutput.length}/{DEFAULT_PHENOTYPES.length} active)</summary>
              <div className="inline-controls compact-actions">
                <button type="button" className="text-action" onClick={() => setSelectedDefaultPhenotypeIds(DEFAULT_PHENOTYPES.map((phenotype) => phenotype.id))}>Select all</button>
                <button type="button" className="text-action" onClick={() => setSelectedDefaultPhenotypeIds([])}>Clear</button>
              </div>
              <div className="option-list">
                {DEFAULT_PHENOTYPES.map((phenotype) => {
                  const isDuplicate = customPhenotypeIds.has(phenotype.id);
                  return (
                    <label className={`option-check${isDuplicate ? " duplicate-option" : ""}`} key={phenotype.id} aria-label={`Include ${phenotype.id}`}>
                      <input
                        type="checkbox"
                        checked={selectedDefaultPhenotypeIds.includes(phenotype.id) && !isDuplicate}
                        disabled={isDuplicate}
                        onChange={() => toggleDefaultPhenotype(phenotype.id)}
                      />
                      <span>{phenotype.id}{isDuplicate && <small>custom</small>}</span>
                    </label>
                  );
                })}
              </div>
            </details>
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
          <div className="metric"><span>Identity fields</span><strong>{selectedIdentityColumns.length}</strong></div>
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
