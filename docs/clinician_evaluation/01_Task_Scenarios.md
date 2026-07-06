# CardioKB Evaluation — Task Scenarios

**Study Title**: Domain Expert Evaluation of CardioKB: A Cardiovascular Disease Knowledge Graph
**Institution**: Cedars-Sinai Medical Center
**Target Evaluators**: CVD clinicians and researchers (N = 5–10)
**Estimated Time**: 30–45 minutes

---

## Instructions for Evaluators

Thank you for participating in this evaluation. CardioKB is a biomedical knowledge graph that integrates 23 data sources into a single searchable network of genes, drugs, diseases, pathways, clinical trials, phenotypes, genetic variants, and more — all focused on cardiovascular disease.

You will complete **5 tasks** using the CardioKB web interface. For each task, please:

1. **Read the clinical scenario** to understand the motivation.
2. **Follow the steps** to complete the task in the tool.
3. **Record your answers** on the evaluation form provided.

There are no right or wrong answers — we are evaluating the tool, not you. Please think aloud or take notes on anything confusing, surprising, or missing.

---

## Task 1: Gene–Disease Investigation

**Scenario**: You are investigating the role of *PCSK9* in cardiovascular disease and want to quickly see what is known about its biological context — associated diseases, drugs targeting it, relevant pathways, and phenotypes.

**Steps**:
1. Go to the **Explore** tab.
2. Type `PCSK9` in the search bar and click **Search**.
3. Examine the resulting graph visualization.

**Questions to answer on the evaluation form**:
- How many node types (colors) appear connected to PCSK9?
- Can you identify at least one drug, one disease, and one pathway connected to PCSK9?
- Click on an edge (line) between PCSK9 and a connected node. What information appears in the tooltip?
- Does this network match your existing knowledge of PCSK9? Is anything important missing?

---

## Task 2: Treatment Lookup via Natural Language

**Scenario**: A colleague asks you what drugs are known to treat atrial fibrillation. Instead of searching multiple databases, you want to ask CardioKB in plain English.

**Steps**:
1. Go to the **Query** tab.
2. In the natural language input bar at the top, type:
   `What drugs treat atrial fibrillation?`
3. Click **Ask AI** and wait for results.
4. Review the results panel that appears (table and/or graph view).

**Questions to answer on the evaluation form**:
- Did the system return a list of drugs? Approximately how many?
- Do you recognize any of these drugs as established treatments for atrial fibrillation?
- Are there any drugs in the results that surprise you (either expected but missing, or unexpected but present)?
- Try a second question of your own choosing (e.g., `What genes are associated with heart failure?`). Did it work?

---

## Task 3: Drug Repurposing Exploration

**Scenario**: You are interested in computational drug repurposing — identifying existing drugs that might treat a disease they were not originally designed for. CardioKB includes ML-predicted drug–disease links based on graph embedding methods (RotatE and CompGCN).

**Steps**:
1. Go to the **Explore** tab.
2. Search for `heart failure`.
3. In the toolbar, check the **"Show ML Predictions"** toggle.
4. Observe the **cyan dashed edges** that appear — these are ML-predicted drug–disease links.
5. Click on a cyan dashed edge to see the prediction details (method and confidence score).
6. Optionally, click **"View Predictions Table"** in the Drug Repurposing panel to see a sortable list.

**Questions to answer on the evaluation form**:
- How many predicted drug repurposing candidates appeared for heart failure?
- Pick one predicted drug. Is this drug currently used for a different indication? Does the repurposing prediction seem biologically plausible to you?
- Is the distinction between known relationships (solid lines) and ML predictions (dashed cyan lines) clear?
- How useful is the confidence score shown for each prediction? What confidence threshold would you consider worth investigating further?

---

## Task 4: Variant-to-Drug Path Tracing

**Scenario**: A patient has a pathogenic variant in *SCN5A*, a gene associated with cardiac channelopathies. You want to trace the biological path from this genetic variant through the gene to associated diseases and potential treatments.

**Steps**:
1. Go to the **Explore** tab.
2. Search for `SCN5A`.
3. In the graph, identify:
   - **Variant** nodes connected to SCN5A (if any).
   - **Disease** nodes connected to SCN5A.
   - **Drug** nodes connected to SCN5A (if any).
4. Click on nodes and edges to explore tooltips and source annotations.
5. Optionally, go to the **Query** tab and ask:
   `What diseases are associated with SCN5A?`

**Questions to answer on the evaluation form**:
- Were you able to trace a path from variant → gene → disease?
- Could you identify any drugs connected to SCN5A or its associated diseases?
- Are the source annotations on edges (e.g., "OpenTargets", "ClinVar", "DrugBank") useful for assessing evidence quality?
- Does the graph reveal any connections you did not already know about?

---

## Task 5: Disease Subgraph Extraction and Export

**Scenario**: You are preparing a dataset for a computational analysis of hypertrophic cardiomyopathy (HCM). You need a structured export of all entities and relationships within 2 hops of HCM in the knowledge graph.

**Steps**:
1. In the **sidebar** (left panel), find the **"Extract Disease Subgraph"** section.
2. Type `hypertrophic cardiomyopathy` in the disease input.
3. Set the hop slider to **2**.
4. Click **Build Subgraph**.
5. Review the summary statistics that appear (node count, relationship count, types).
6. Click **Export JSON** or **Export CSV** to download the data.
7. Open the downloaded file briefly to inspect its structure.

**Questions to answer on the evaluation form**:
- Did the subgraph extraction complete successfully? How many nodes and relationships were returned?
- Does the exported data structure (JSON or CSV) look usable for downstream analysis (e.g., in Python, R, or Excel)?
- Is the 1–3 hop range sufficient for your use case, or would you need more?
- Would you use this feature to generate datasets for your own research? Why or why not?

---

## After Completing All Tasks

Please fill out the **CardioKB Evaluation Form** (provided separately). It takes approximately 10 minutes and includes:
- A standard usability questionnaire (10 questions)
- Domain-specific questions about accuracy, completeness, and clinical relevance
- Open-ended feedback

Thank you for your time and expertise.
