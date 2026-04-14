#!/usr/bin/env python3
"""
Fix ClinicalTrial → Disease (STUDIES_CONDITION) edges.

Problem: ClinicalTrials.gov uses clinical/lay condition names like
"Heart Failure", "Coronary Artery Disease" while Disease Ontology uses
formal names like "congestive heart failure". Only 674 of 82,070 trials
are connected.

Solution: Multi-strategy fuzzy matching:
  1. Exact match (case-insensitive)
  2. Normalized match (strip parentheticals, trailing qualifiers)
  3. Substring containment (condition in disease name or vice versa)
  4. Manual synonym map for top unmatched CVD conditions
"""

import os
import re
import sys
from collections import defaultdict

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# ── Manual synonym map for high-frequency clinical terms ──────────────
# Maps lowercased ClinicalTrials.gov condition → Disease Ontology commonName
MANUAL_MAP = {
    # Heart failure variants
    "heart failure": "congestive heart failure",
    "chronic heart failure": "congestive heart failure",
    "acute heart failure": "congestive heart failure",
    "congestive heart failure": "congestive heart failure",
    "heart failure, diastolic": "diastolic heart failure",
    "heart failure, systolic": "systolic heart failure",
    "heart failure with reduced ejection fraction": "systolic heart failure",
    "heart failure with preserved ejection fraction": "diastolic heart failure",
    "hfref": "systolic heart failure",
    "hfpef": "diastolic heart failure",
    "left heart failure": "left-sided congestive heart failure",
    "right heart failure": "right-sided congestive heart failure",
    # Coronary
    "coronary artery disease": "coronary artery disease",
    "coronary disease": "coronary artery disease",
    "coronary heart disease": "coronary artery disease",
    "ischemic heart disease": "coronary artery disease",
    "cad": "coronary artery disease",
    # MI
    "myocardial infarction": "myocardial infarction",
    "acute myocardial infarction": "myocardial infarction",
    "heart attack": "myocardial infarction",
    "mi": "myocardial infarction",
    "stemi": "myocardial infarction",
    "nstemi": "myocardial infarction",
    "st elevation myocardial infarction": "myocardial infarction",
    "non-st elevation myocardial infarction": "myocardial infarction",
    # Stroke
    "stroke": "cerebrovascular disease",
    "ischemic stroke": "ischemic stroke",
    "acute ischemic stroke": "ischemic stroke",
    "hemorrhagic stroke": "hemorrhagic stroke",
    "cerebrovascular accident": "cerebrovascular disease",
    "stroke, acute": "cerebrovascular disease",
    "stroke, ischemic": "ischemic stroke",
    "cerebral infarction": "cerebral infarction",
    "transient ischemic attack": "transient ischemic attack",
    # Hypertension
    "hypertension": "hypertension",
    "high blood pressure": "hypertension",
    "essential hypertension": "essential hypertension",
    "pulmonary hypertension": "pulmonary hypertension",
    "pulmonary arterial hypertension": "primary pulmonary hypertension",
    "resistant hypertension": "hypertension",
    # Arrhythmia
    "atrial fibrillation": "atrial fibrillation",
    "ventricular tachycardia": "ventricular tachycardia",
    "cardiac arrhythmia": "cardiac arrhythmia",
    "arrhythmia": "cardiac arrhythmia",
    "supraventricular tachycardia": "supraventricular tachycardia",
    "atrial flutter": "atrial flutter",
    "ventricular fibrillation": "ventricular fibrillation",
    "long qt syndrome": "long QT syndrome",
    "brugada syndrome": "Brugada syndrome",
    "cardiac arrest": "cardiac arrest",
    "sudden cardiac death": "sudden cardiac death",
    # Cardiomyopathy
    "cardiomyopathy": "cardiomyopathy",
    "dilated cardiomyopathy": "dilated cardiomyopathy",
    "hypertrophic cardiomyopathy": "familial hypertrophic cardiomyopathy",
    "hcm": "familial hypertrophic cardiomyopathy",
    # Valve
    "aortic stenosis": "aortic valve stenosis",
    "aortic valve stenosis": "aortic valve stenosis",
    "mitral regurgitation": "mitral valve insufficiency",
    "mitral valve regurgitation": "mitral valve insufficiency",
    "mitral valve prolapse": "mitral valve prolapse",
    "aortic regurgitation": "aortic valve insufficiency",
    "aortic valve disease": "aortic valve disease",
    # Vascular
    "atherosclerosis": "atherosclerosis",
    "peripheral arterial disease": "peripheral artery disease",
    "peripheral artery disease": "peripheral artery disease",
    "peripheral vascular disease": "peripheral vascular disease",
    "aortic aneurysm": "aortic aneurysm",
    "abdominal aortic aneurysm": "abdominal aortic aneurysm",
    "deep vein thrombosis": "deep vein thrombosis",
    "venous thromboembolism": "venous thromboembolism",
    "pulmonary embolism": "pulmonary embolism",
    "thrombosis": "thrombosis",
    "aortic dissection": "aortic dissection",
    # Other cardiac
    "myocarditis": "myocarditis",
    "pericarditis": "pericarditis",
    "endocarditis": "endocarditis",
    "congenital heart disease": "congenital heart disease",
    "congenital heart defect": "congenital heart disease",
    "angina": "angina pectoris",
    "angina pectoris": "angina pectoris",
    "unstable angina": "unstable angina",
    "acute coronary syndrome": "acute coronary syndrome",
    # Metabolic / risk factors
    "diabetes": "diabetes mellitus",
    "diabetes mellitus": "diabetes mellitus",
    "diabetes mellitus, type 2": "type 2 diabetes mellitus",
    "type 2 diabetes": "type 2 diabetes mellitus",
    "type 2 diabetes mellitus": "type 2 diabetes mellitus",
    "type 1 diabetes": "type 1 diabetes mellitus",
    "type 1 diabetes mellitus": "type 1 diabetes mellitus",
    "obesity": "obesity",
    "metabolic syndrome": "metabolic syndrome X",
    "hyperlipidemia": "hyperlipidemia",
    "hypercholesterolemia": "hypercholesterolemia",
    "dyslipidemia": "dyslipidemia",
    "dyslipidemias": "dyslipidemia",
    # Kidney (CVD comorbidity)
    "chronic kidney disease": "chronic kidney disease",
    "renal insufficiency": "renal insufficiency",
    "acute kidney injury": "acute kidney tubular necrosis",
    # Other
    "sepsis": "septicemia",
    "pneumonia": "pneumonia",
    "covid-19": "COVID-19",
    "preeclampsia": "pre-eclampsia",
    "eclampsia": "eclampsia",
    "anemia": "anemia",
    "sleep apnea": "sleep apnea",
    "obstructive sleep apnea": "obstructive sleep apnea",
    # Additional high-frequency unmatched
    "venous thromboembolism": "venous thromboembolism",
    "dyslipidemia": "dyslipidemia",
    "dyslipidemias": "dyslipidemia",
    "cerebrovascular accident": "cerebrovascular disease",
    "stroke, acute": "cerebrovascular disease",
    "heart failure, congestive": "congestive heart failure",
    "subarachnoid hemorrhage": "subarachnoid hemorrhage",
    "intracerebral hemorrhage": "intracerebral hemorrhage",
    "bradycardia": "bradycardia",
    "tachycardia": "tachycardia",
    "diabetic foot ulcer": "diabetic foot ulcer",
    "diabetic foot": "diabetic foot",
    "insulin resistance": "insulin resistance",
    "cardiac disease": "heart disease",
    "heart diseases": "heart disease",
    "cardiovascular diseases": "cardiovascular system disease",
    "cardiovascular disease": "cardiovascular system disease",
    "vascular diseases": "vascular disease",
    "blood pressure": "hypertension",
    "cardiac arrest": "cardiac arrest",
    "carotid artery stenosis": "carotid stenosis",
    "carotid stenosis": "carotid stenosis",
    "aortic valve stenosis": "aortic valve stenosis",
    "intracranial hemorrhage": "intracranial hemorrhage",
    "cardiac failure": "congestive heart failure",
    "diabetic nephropathy": "diabetic nephropathy",
    "diabetic retinopathy": "diabetic retinopathy",
    "diabetic neuropathy": "diabetic neuropathy",
    "chronic obstructive pulmonary disease": "chronic obstructive pulmonary disease",
    "copd": "chronic obstructive pulmonary disease",
    "kidney failure": "renal failure",
    "end stage renal disease": "end stage renal failure",
    "chronic kidney failure": "chronic renal failure",
    "myocardial fibrosis": "myocardial fibrosis",
    "aortic regurgitation": "aortic valve insufficiency",
    "tricuspid regurgitation": "tricuspid valve insufficiency",
    "cardiac fibrosis": "cardiac fibrosis",
    "coronary artery stenosis": "coronary stenosis",
    "left ventricular dysfunction": "left ventricular failure",
    "left ventricular hypertrophy": "left ventricular hypertrophy",
    "right ventricular dysfunction": "right-sided congestive heart failure",
    "cardiac hypertrophy": "cardiac hypertrophy",
    "heart valve disease": "heart valve disease",
    "valvular heart disease": "heart valve disease",
}


def normalize(s: str) -> str:
    """Normalize a condition string for matching."""
    s = s.lower().strip()
    # Remove parenthetical text: "Acute Heart Failure (AHF)" -> "acute heart failure"
    s = re.sub(r'\s*\([^)]*\)', '', s)
    # Remove trailing qualifiers after comma if they're just numbers/types
    # e.g. "Diabetes Mellitus, Type 2" kept as-is (useful), but
    # "Heart Failure, Congestive" -> keep
    s = s.strip(' ,;.')
    return s


def run():
    driver = GraphDatabase.driver(
        os.getenv("MEMGRAPH_URI", "bolt://localhost:7687"),
        auth=(os.getenv("MEMGRAPH_USERNAME", ""), os.getenv("MEMGRAPH_PASSWORD")),
    )

    with driver.session() as session:
        # ── Step 1: Load all Disease nodes ──────────────────────────────
        print("Loading Disease nodes...")
        result = session.run(
            "MATCH (d:Disease) "
            "RETURN id(d) AS eid, d.commonName AS name"
        )
        # Build lookup: lowercased name -> elementId
        disease_by_name = {}
        for rec in result:
            name = rec["name"]
            if name:
                disease_by_name[name.lower()] = rec["eid"]

        print(f"  {len(disease_by_name)} unique Disease names loaded")

        # ── Step 2: Load all ClinicalTrial condition strings ────────────
        print("Loading ClinicalTrial conditions...")
        result = session.run(
            "MATCH (ct:ClinicalTrial) "
            "WHERE ct.condition IS NOT NULL AND ct.condition <> 'Not specified' "
            "RETURN id(ct) AS eid, ct.condition AS cond"
        )
        # Split multi-condition strings; build condition -> [trial_eids]
        cond_to_trials = defaultdict(list)
        for rec in result:
            raw = rec["cond"]
            for part in raw.split("; "):
                part = part.strip()
                if part:
                    cond_to_trials[part].append(rec["eid"])

        unique_conds = list(cond_to_trials.keys())
        print(f"  {len(unique_conds)} unique condition strings across "
              f"{sum(len(v) for v in cond_to_trials.values())} trial-condition pairs")

        # ── Step 3: Match conditions to diseases ────────────────────────
        print("Matching conditions to diseases...")
        matched = {}   # condition_string -> disease_eid
        unmatched = []

        for cond in unique_conds:
            cond_lower = cond.lower()
            cond_norm = normalize(cond)

            # Strategy 1: Exact (case-insensitive)
            if cond_lower in disease_by_name:
                matched[cond] = disease_by_name[cond_lower]
                continue

            # Strategy 2: Normalized
            if cond_norm in disease_by_name:
                matched[cond] = disease_by_name[cond_norm]
                continue

            # Strategy 3: Manual synonym map
            if cond_lower in MANUAL_MAP:
                target = MANUAL_MAP[cond_lower].lower()
                if target in disease_by_name:
                    matched[cond] = disease_by_name[target]
                    continue

            if cond_norm in MANUAL_MAP:
                target = MANUAL_MAP[cond_norm].lower()
                if target in disease_by_name:
                    matched[cond] = disease_by_name[target]
                    continue

            # Strategy 4: Substring containment
            # Check if any Disease name is contained in the condition or vice versa
            # Prefer longest match (most specific disease)
            best_match = None
            best_len = 0
            for dname, deid in disease_by_name.items():
                if len(dname) < 5:  # skip very short names
                    continue
                if dname in cond_norm and len(dname) > best_len:
                    best_match = deid
                    best_len = len(dname)
                elif cond_norm in dname and len(cond_norm) > best_len:
                    best_match = deid
                    best_len = len(cond_norm)
            if best_match and best_len >= 8:
                matched[cond] = best_match
                continue

            unmatched.append(cond)

        # Stats
        matched_trials = sum(len(cond_to_trials[c]) for c in matched)
        unmatched_trials = sum(len(cond_to_trials[c]) for c in unmatched)
        print(f"  Matched: {len(matched)} conditions ({matched_trials} trial-condition pairs)")
        print(f"  Unmatched: {len(unmatched)} conditions ({unmatched_trials} trial-condition pairs)")

        # Show top unmatched
        top_unmatched = sorted(unmatched, key=lambda c: len(cond_to_trials[c]), reverse=True)[:20]
        print("\n  Top unmatched conditions:")
        for c in top_unmatched:
            print(f"    {len(cond_to_trials[c]):>5}  {c}")

        # ── Step 4: Create STUDIES_CONDITION edges ──────────────────────
        print(f"\nCreating STUDIES_CONDITION edges...")
        # Build batch: list of {trial_eid, disease_eid}
        pairs = []
        for cond, disease_eid in matched.items():
            for trial_eid in cond_to_trials[cond]:
                pairs.append({"trial_eid": trial_eid, "disease_eid": disease_eid})

        # Deduplicate (a trial may have multiple conditions mapping to same disease)
        seen = set()
        deduped = []
        for p in pairs:
            key = (p["trial_eid"], p["disease_eid"])
            if key not in seen:
                seen.add(key)
                deduped.append(p)
        pairs = deduped
        print(f"  {len(pairs)} unique trial→disease pairs to create")

        # Batch MERGE
        batch_size = 2000
        total_created = 0
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i + batch_size]
            result = session.run(
                'UNWIND $rows AS row '
                'MATCH (ct:ClinicalTrial) WHERE id(ct) = row.trial_eid '
                'MATCH (d:Disease) WHERE id(d) = row.disease_eid '
                'MERGE (ct)-[r:STUDIES_CONDITION]->(d) '
                'ON CREATE SET r.source = "ClinicalTrials.gov" '
                'RETURN count(r) AS cnt',
                rows=batch,
            )
            cnt = result.single()["cnt"]
            total_created += cnt
            print(f"  Batch {i // batch_size + 1}: {total_created} edges so far")

        print(f"\nDone! Created {total_created} STUDIES_CONDITION edges total.")

        # Final verification
        result = session.run(
            "MATCH (ct:ClinicalTrial)-[:STUDIES_CONDITION]->() "
            "RETURN count(DISTINCT ct) AS connected"
        )
        print(f"Connected ClinicalTrial nodes: {result.single()['connected']} / 82,070")

    driver.close()


if __name__ == "__main__":
    run()
