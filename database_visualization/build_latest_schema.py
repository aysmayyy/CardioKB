#!/usr/bin/env python3
"""
Build a self-contained version of cardiokb_source_schema_template.html that works
when opened directly from the filesystem (file:// protocol).

Usage:
    python database_visualization/build_latest_schema.py

Output:
    database_visualization/cardiokb_source_schema_latest.html
"""

import csv
import json
from pathlib import Path

DOCS = Path(__file__).parent
CSV_PATH = DOCS / "cardiokb_databases.csv"
TEMPLATE_PATH = DOCS / "cardiokb_source_schema_template.html"
OUTPUT_PATH = DOCS / "cardiokb_source_schema_latest.html"

PLACEHOLDER = "const DB_DATA = null; // @INJECT"

# Must mirror CKB_NODE_TYPES in cardiokb_source_schema_template.html
NODE_LABEL_TO_ID = {
    "Gene":                "nt_Gene",
    "Disease":             "nt_Disease",
    "Drug":                "nt_Drug",
    "Variant":             "nt_Variant",
    "ClinicalTrial":       "nt_ClinicalTrial",
    "Pathway":             "nt_Pathway",
    "TranscriptionFactor": "nt_TranscriptionFactor",
    "BiologicalProcess":   "nt_BiologicalProcess",
    "MolecularFunction":   "nt_MolecularFunction",
    "CellularComponent":   "nt_CellularComponent",
    "BodyPart":            "nt_BodyPart",
    "Symptom":             "nt_Symptom",
    "SideEffect":          "nt_SideEffect",
    "Phenotype":           "nt_Phenotype",
    "PharmacologicClass":  "nt_PharmacologicClass",
    "GeneFamily":          "nt_GeneFamily",
    "DrugLabel":           "nt_DrugLabel",
    "AgeingProperty":      "nt_AgeingProperty",
    "Species":             "nt_Species",
}

# Must mirror CKB_EDGE_TYPES in cardiokb_source_schema_template.html
EDGE_LABEL_TO_ID = {
    "geneAssociatesWithDisease":            "et_GAD",
    "geneInteractsWithGene":                "et_GIG",
    "geneRegulatesGene":                    "et_GRG",
    "geneParticipatesInBiologicalProcess":  "et_GBP",
    "geneHasMolecularFunction":             "et_GMF",
    "geneAssociatedWithCellularComponent":  "et_GCC",
    "geneInPathway":                        "et_GIP",
    "pathwayContainsGene":                  "et_PCG",
    "geneAssociatesWithPhenotype":          "et_GAP",
    "geneExpressedInBodyPart":              "et_GEB",
    "bodyPartOverexpressesGene":            "et_BOG",
    "bodyPartUnderexpressesGene":           "et_BUG",
    "geneInFamily":                         "et_GIF",
    "familyContainsGene":                   "et_FCG",
    "hasVariant":                           "et_HV",
    "variantInGene":                        "et_VIG",
    "associatedWithVariant":                "et_AWV",
    "variantAssociatedWithDisease":         "et_VAD",
    "transcriptionFactorInteractsWithGene": "et_TFG",
    "drugBindsGene":                        "et_DBG",
    "chemicalBindsGene":                    "et_CBG",
    "chemicalIncreasesExpression":          "et_CIE",
    "chemicalDecreasesExpression":          "et_CDE",
    "compoundUpregulatesGene":              "et_CUG",
    "compoundDownregulatesGene":            "et_CDG",
    "drugTreatsDisease":                    "et_DTD",
    "drugPalliatesDisease":                 "et_DPD",
    "compoundCausesSideEffect":             "et_CCE",
    "pharmacologicClassIncludesCompound":   "et_PCI",
    "compoundInPharmacologicClass":         "et_CPC",
    "diseaseAssociatesWithDisease":         "et_DAD",
    "diseaseResemblesDisease":              "et_DRD",
    "diseasePresentsSymptom":               "et_DPS",
    "diseaseLocalizesToAnatomy":            "et_DLA",
    "STUDIES_CONDITION":                    "et_SC",
    "TESTS_INTERVENTION":                   "et_TI",
    "VARIANT_IN":                           "et_VI",
    "AFFECTS_RESPONSE_TO":                  "et_ART",
    "drugLabelAnnotatesGene":               "et_DLAG",
    "drugLabelDescribesDrug":               "et_DLDD",
    "associatedWithAging":                  "et_AWA",
}


def transform_row(row: dict) -> dict | None:
    """Apply the same transformation as parseCSV() in the template."""
    db_id = row.get("ID", "").strip()
    if not db_id:
        return None

    raw_nodes = row.get("Biomedical Entities (Node types)", "").strip()
    raw_edges = row.get("Biomedical Relationships (Edge types)", "").strip()

    nodes = [NODE_LABEL_TO_ID[s.strip()] for s in raw_nodes.split(",")
             if raw_nodes and s.strip() in NODE_LABEL_TO_ID]
    edges = [EDGE_LABEL_TO_ID[s.strip()] for s in raw_edges.split(",")
             if raw_edges and s.strip() in EDGE_LABEL_TO_ID]

    return {
        "id":          db_id,
        "label":       row.get("Label", "").strip(),
        "integration": row.get("Integration Path", "").strip(),
        "active":      row.get("Active", "").strip() == "Yes",
        "version":     row.get("Latest Version", "").strip() or "N/A",
        "parent":      row.get("Sub-source Of", "").strip() or None,
        "nodes":       nodes,
        "edges":       edges,
    }


def main():
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        dbs = [r for row in csv.DictReader(f) if (r := transform_row(row))]

    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    if PLACEHOLDER not in template:
        raise RuntimeError(f"Placeholder not found in template: {PLACEHOLDER!r}")

    injected = f"const DB_DATA = {json.dumps(dbs, ensure_ascii=False, indent=2)};"
    patched = template.replace(PLACEHOLDER, injected, 1)

    OUTPUT_PATH.write_text(patched, encoding="utf-8")
    print(f"Written: {OUTPUT_PATH}  ({len(dbs)} databases)")


if __name__ == "__main__":
    main()
