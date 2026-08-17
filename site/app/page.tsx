"use client";

import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { BASE_COLUMNS, DEFAULT_PHENOTYPES, normalizeWhitespace, parsePhenotypeList, slug } from "./phenotypes";
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

function defaultExtract(reports: ReportText[], phenotypes: PhenotypeDefinition[]) {
  const rows = reports.map((report, index) => {
    const text = report.text;
    const textLower = text.toLowerCase();
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
      dog_id: `${index + 1}_${slug(dogName, "dog")}`,
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
    for (const phenotype of phenotypes) {
      const matchedTerm = phenotype.terms.find((term) => textLower.includes(term.toLowerCase()));
      row[phenotype.id] = matchedTerm ? inferStatus(text, matchedTerm) : "";
      if (matchedTerm) eventCount += 1;
    }
    row.phenotype_event_count = String(eventCount);
    return row;
  });
  return { columns: [...BASE_COLUMNS, ...phenotypes.map((phenotype) => phenotype.id)], rows };
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
  const [files, setFiles] = useState<FileList | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<DatasetRow[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  const visibleColumns = useMemo(() => columns.slice(0, 18), [columns]);
  const customPhenotypes = useMemo(() => parsePhenotypeList(phenotypeText), [phenotypeText]);
  const extractionPhenotypes = customPhenotypes.length ? customPhenotypes : DEFAULT_PHENOTYPES;
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
        const dataset = defaultExtract(reportTexts, extractionPhenotypes);
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
            <legend>{phenotypeStep}. Phenotype List</legend>
            <p className="helper-text">
              Leave this blank to use the default phenotype list. Add one phenotype per line, separate phenotypes with commas, or import a .txt list.
            </p>
            <label className="field">
              <span>Custom phenotype list</span>
              <textarea
                value={phenotypeText}
                onChange={(event) => setPhenotypeText(event.target.value)}
                placeholder={"vomiting\nheart murmur\nskin mass, weight loss"}
              />
            </label>
            <div className="inline-controls">
              <label className="txt-file">
                <span>Import .txt</span>
                <input type="file" accept=".txt,text/plain" onChange={handlePhenotypeFileChange} />
              </label>
              {isCustomPhenotypeList && (
                <button type="button" className="text-action" onClick={() => setPhenotypeText("")}>Use default list</button>
              )}
            </div>
            <p className="helper-text">
              {isCustomPhenotypeList ? `Using ${customPhenotypes.length} custom phenotype columns.` : `Using ${DEFAULT_PHENOTYPES.length} default phenotype columns.`}
            </p>
            <details className="default-phenotypes">
              <summary>Default phenotype list ({DEFAULT_PHENOTYPES.length})</summary>
              <div className="chip-list">
                {DEFAULT_PHENOTYPES.map((phenotype) => <span key={phenotype.id}>{phenotype.id}</span>)}
              </div>
            </details>
          </fieldset>

          <fieldset>
            <legend>{fileStep}. Dog PDF Files</legend>
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
          <div className="metric"><span>Phenotypes</span><strong>{extractionPhenotypes.length}</strong></div>
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
