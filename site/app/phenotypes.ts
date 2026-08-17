export type PhenotypeDefinition = {
  id: string;
  label: string;
  terms: string[];
};

export type DateHit = {
  value: string;
  index: number;
};

export type DatedValue = {
  value: string;
  date?: string;
};

export const DEFAULT_PHENOTYPES: PhenotypeDefinition[] = [
  { id: "diarrhea", label: "diarrhea", terms: ["diarrhea", "loose stool", "soft stool"] },
  { id: "vomiting", label: "vomiting", terms: ["vomiting", "vomited", "vomit"] },
  { id: "decreased_appetite_anorexia", label: "decreased appetite / anorexia", terms: ["decreased appetite", "not eating", "anorexia", "inappetence"] },
  { id: "lethargy", label: "lethargy", terms: ["lethargy", "lethargic"] },
  { id: "cough", label: "cough", terms: ["cough", "coughing"] },
  { id: "sneezing", label: "sneezing", terms: ["sneezing", "sneeze"] },
  { id: "pruritus_itching", label: "pruritus / itching", terms: ["pruritus", "itching", "itchy"] },
  { id: "alopecia", label: "alopecia", terms: ["alopecia", "hair loss"] },
  { id: "otitis", label: "otitis", terms: ["otitis", "ear infection"] },
  { id: "skin_mass_lump", label: "skin mass / lump", terms: ["mass", "lump", "skin mass"] },
  { id: "lameness_limping", label: "lameness / limping", terms: ["lameness", "limping", "limp"] },
  { id: "pain", label: "pain", terms: ["painful", "pain"] },
  { id: "weight_loss", label: "weight loss", terms: ["weight loss", "losing weight"] },
  { id: "underweight", label: "underweight", terms: ["underweight", "thin body condition"] },
  { id: "overweight_obesity", label: "overweight / obesity", terms: ["overweight", "obese", "obesity"] },
  { id: "heart_murmur", label: "heart murmur", terms: ["heart murmur", "murmur"] },
  { id: "dental_disease", label: "dental disease", terms: ["dental disease", "tartar", "gingivitis"] },
  { id: "urinary_tract_infection", label: "urinary tract infection", terms: ["urinary tract infection", "uti"] },
  { id: "proteinuria", label: "proteinuria", terms: ["proteinuria", "protein in urine"] },
  { id: "anxiety_nervousness", label: "anxiety / nervousness", terms: ["anxiety", "nervous", "fearful"] },
  { id: "wound_laceration_ulcer", label: "wound / laceration / ulcer", terms: ["wound", "laceration", "ulcer"] },
  { id: "allergic_dermatitis", label: "allergic dermatitis", terms: ["allergic dermatitis", "atopy", "allergy"] },
  { id: "pyoderma", label: "pyoderma", terms: ["pyoderma"] },
  { id: "pancreatitis", label: "pancreatitis", terms: ["pancreatitis"] },
  { id: "giardia", label: "giardia", terms: ["giardia"] },
  { id: "roundworm_infection", label: "roundworm infection", terms: ["roundworm"] },
];

export const IDENTITY_COLUMNS = [
  "dog_id",
  "source_file",
  "dog_name",
  "patient_id",
  "species",
  "breed_raw",
  "sex",
  "reproductive_status",
  "color",
  "weight",
  "date_of_birth",
  "age_reported",
  "visit_dates",
];

export const META_COLUMNS = [
  "phenotype_event_count",
];

export const BASE_COLUMNS = [
  ...IDENTITY_COLUMNS,
  ...META_COLUMNS,
];

const MONTHS: Record<string, string> = {
  jan: "01",
  january: "01",
  feb: "02",
  february: "02",
  mar: "03",
  march: "03",
  apr: "04",
  april: "04",
  may: "05",
  jun: "06",
  june: "06",
  jul: "07",
  july: "07",
  aug: "08",
  august: "08",
  sep: "09",
  sept: "09",
  september: "09",
  oct: "10",
  october: "10",
  nov: "11",
  november: "11",
  dec: "12",
  december: "12",
};

export function normalizeWhitespace(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

export function slug(value: string, fallback = "phenotype") {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || fallback;
}

function normalizeYear(value: string) {
  const year = Number(value);
  if (value.length === 2) return year >= 50 ? `19${value}` : `20${value}`;
  return value.padStart(4, "0");
}

function validMonthDay(month: number, day: number) {
  return month >= 1 && month <= 12 && day >= 1 && day <= 31;
}

function formatDate(month: string, day: string, year: string) {
  const monthNumber = Number(month);
  const dayNumber = Number(day);
  if (!validMonthDay(monthNumber, dayNumber)) return "";
  return `${String(monthNumber).padStart(2, "0")}/${String(dayNumber).padStart(2, "0")}/${normalizeYear(year)}`;
}

export function standardizeDate(raw: string) {
  const clean = normalizeWhitespace(raw.replace(/,/g, " ").replace(/\./g, ""));
  let match = clean.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  if (match) return formatDate(match[2], match[3], match[1]);

  match = clean.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$/);
  if (match) return formatDate(match[1], match[2], match[3]);

  match = clean.match(/^([A-Za-z]+)\s+(\d{1,2})\s+(\d{2,4})$/);
  if (match) {
    const month = MONTHS[match[1].toLowerCase()];
    if (month) return formatDate(month, match[2], match[3]);
  }

  return "";
}

export function findDateHits(text: string, excludeBirthDates = true): DateHit[] {
  const pattern = /\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{2,4})\b/gi;
  const hits: DateHit[] = [];
  for (const match of text.matchAll(pattern)) {
    const raw = match[0];
    const value = standardizeDate(raw);
    if (!value) continue;
    const index = match.index ?? 0;
    const context = text.slice(Math.max(0, index - 35), index).toLowerCase();
    if (excludeBirthDates && /\b(?:dob|d\.o\.b|birth|birthday|date of birth)\b/.test(context)) continue;
    hits.push({ value, index });
  }
  return hits;
}

export function uniqueDates(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => {
    const aKey = a.slice(6) + a.slice(0, 2) + a.slice(3, 5);
    const bKey = b.slice(6) + b.slice(0, 2) + b.slice(3, 5);
    return aKey.localeCompare(bKey);
  });
}

export function nearestDateForIndex(dateHits: DateHit[], index: number) {
  if (!dateHits.length) return "";
  const before = dateHits.filter((hit) => hit.index <= index).at(-1);
  if (before) return before.value;
  return dateHits[0].value;
}

export function formatDateList(dates: string[]) {
  const values = uniqueDates(dates);
  if (!values.length) return "";
  return values.length === 1 ? values[0] : JSON.stringify(values);
}

export function normalizeColor(raw: string) {
  const cleaned = normalizeWhitespace(raw)
    .toLowerCase()
    .replace(/\b(?:color|colour|coat)\b\s*:?\s*/g, "")
    .replace(/\b(?:unknown|not recorded|n\/a)\b/g, "")
    .replace(/\s+/g, " ");
  const parts = cleaned
    .split(/\s*(?:,|\/|&|\+|\band\b)\s*/i)
    .map((part) => part.replace(/[.;:]$/g, "").trim())
    .filter(Boolean);
  return Array.from(new Set(parts)).join(", ");
}

export function normalizeSpecies(raw: string) {
  const value = normalizeWhitespace(raw).toLowerCase();
  if (/\b(?:canine|dog|canis)\b/.test(value)) return "canine";
  return value;
}

export function normalizeSex(raw: string) {
  const value = normalizeWhitespace(raw).toLowerCase();
  if (/\b(?:female|fs|sf|spayed female|f\/s)\b/.test(value)) return "female";
  if (/\b(?:male|mn|nm|neutered male|m\/n)\b/.test(value)) return "male";
  return value;
}

export function normalizeReproductiveStatus(raw: string) {
  const value = normalizeWhitespace(raw).toLowerCase();
  if (/\b(?:spay|spayed|fs|sf|f\/s)\b/.test(value)) return "spayed";
  if (/\b(?:neuter|neutered|castrated|mn|nm|m\/n)\b/.test(value)) return "neutered";
  if (/\b(?:intact|entire)\b/.test(value)) return "intact";
  return "";
}

export function normalizeWeight(raw: string) {
  return normalizeWhitespace(raw)
    .toLowerCase()
    .replace(/\bpounds?\b/g, "lb")
    .replace(/\blbs?\b/g, "lb")
    .replace(/\bkilograms?\b/g, "kg")
    .replace(/\bkgs?\b/g, "kg");
}

export function formatObservedValues(observations: DatedValue[]) {
  const grouped = new Map<string, Set<string>>();
  for (const observation of observations) {
    const value = normalizeWhitespace(observation.value);
    if (!value) continue;
    if (!grouped.has(value)) grouped.set(value, new Set());
    if (observation.date) grouped.get(value)?.add(observation.date);
  }

  if (!grouped.size) return "";
  if (grouped.size === 1) return Array.from(grouped.keys())[0];

  const output: Record<string, string | string[]> = {};
  for (const [value, dates] of grouped) {
    const dateList = uniqueDates(Array.from(dates));
    output[value] = dateList.length > 1 ? dateList : dateList[0] || "";
  }
  return JSON.stringify(output);
}

export function formatDatedStatusValues(events: DatedValue[]) {
  const grouped = new Map<string, Set<string>>();
  for (const event of events) {
    const value = normalizeWhitespace(event.value);
    if (!value) continue;
    if (!grouped.has(value)) grouped.set(value, new Set());
    if (event.date) grouped.get(value)?.add(event.date);
  }

  if (!grouped.size) return "";
  const output: Record<string, string | string[]> = {};
  for (const [value, dates] of grouped) {
    const dateList = uniqueDates(Array.from(dates));
    output[value] = dateList.length > 1 ? dateList : dateList[0] || "";
  }
  return JSON.stringify(output);
}

export function parsePhenotypeList(raw: string): PhenotypeDefinition[] {
  const seen = new Set<string>();
  const entries = raw
    .split(/[\n,]+/)
    .map((entry) => normalizeWhitespace(entry.replace(/^\s*(?:[-*]|\d+[.)])\s*/, "")))
    .filter(Boolean);

  const phenotypes: PhenotypeDefinition[] = [];
  for (const entry of entries) {
    const id = slug(entry);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const displayTerm = entry.replace(/_/g, " ");
    const idTerm = id.replace(/_/g, " ");
    phenotypes.push({
      id,
      label: entry,
      terms: Array.from(new Set([entry, displayTerm, idTerm])).filter(Boolean),
    });
  }
  return phenotypes;
}

export function mergePhenotypes(customPhenotypes: PhenotypeDefinition[], includeDefaultPhenotypes: boolean) {
  const seen = new Set<string>();
  const merged: PhenotypeDefinition[] = [];

  for (const phenotype of customPhenotypes) {
    if (seen.has(phenotype.id)) continue;
    seen.add(phenotype.id);
    merged.push(phenotype);
  }

  if (includeDefaultPhenotypes) {
    for (const phenotype of DEFAULT_PHENOTYPES) {
      if (seen.has(phenotype.id)) continue;
      seen.add(phenotype.id);
      merged.push(phenotype);
    }
  }

  return merged;
}

export function buildDatasetColumns(includeIdentityColumns: boolean, phenotypes: PhenotypeDefinition[]) {
  return [
    ...(includeIdentityColumns ? IDENTITY_COLUMNS : []),
    ...(phenotypes.length ? META_COLUMNS : []),
    ...phenotypes.map((phenotype) => phenotype.id),
  ];
}
