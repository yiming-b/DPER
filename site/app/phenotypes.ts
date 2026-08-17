export type PhenotypeDefinition = {
  id: string;
  label: string;
  terms: string[];
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

export const BASE_COLUMNS = [
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

export function normalizeWhitespace(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

export function slug(value: string, fallback = "phenotype") {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || fallback;
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
