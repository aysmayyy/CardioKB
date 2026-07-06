# CardioKB — Quick Start Guide

> **What is CardioKB?** A cardiovascular disease knowledge graph integrating 23 biomedical databases — genes, drugs, diseases, pathways, clinical trials, phenotypes, and genetic variants — into a single searchable, visual network.

---

## Accessing CardioKB

Open in your browser: **[URL will be provided by the study coordinator]**

No login or installation required. Works in Chrome, Firefox, Safari, or Edge.

---

## Interface Overview

CardioKB has **two main tabs** and a **sidebar** with additional tools.

### Explore Tab — Visual Graph Browser

<!-- SCREENSHOT PLACEHOLDER: Capture the Explore tab showing a search result
     (e.g., search "atrial fibrillation"). Include the search bar, graph
     visualization, legend panel, and ML predictions toggle. -->

> **[Screenshot: Explore tab with graph visualization]**

| What you see | What it means |
|---|---|
| **Search bar** (top) | Type any gene, drug, or disease name and click **Search** |
| **Colored nodes** | Each color = a different entity type (gene, drug, disease, etc.) — see the legend |
| **Solid gray edges** | Known relationships from curated databases. Click to see source |
| **Cyan dashed edges** | ML-predicted drug–disease links (hidden by default) |
| **"Show ML Predictions" toggle** | Enable to overlay computational drug repurposing predictions |
| **Node tooltips** | Click any node to see its properties and identifiers |
| **Edge tooltips** | Click any edge to see the relationship type and source database |
| **Export buttons** (bottom right) | Download the current graph as CSV or JSON |

**Tip**: After searching, the graph stabilizes automatically. You can drag nodes to rearrange, scroll to zoom, and drag the background to pan.

---

### Query Tab — Ask Questions in Plain English or Cypher

<!-- SCREENSHOT PLACEHOLDER: Capture the Query tab showing (1) the natural
     language input bar with an example question typed in, and (2) a results
     panel with table + graph sub-tabs. -->

> **[Screenshot: Query tab with natural language input and results panel]**

| What you see | What it means |
|---|---|
| **Natural language bar** (top) | Type a question in plain English (e.g., "What drugs treat heart failure?") and click **Ask AI** |
| **Cypher input** (below) | For advanced users: write raw Cypher queries directly |
| **Results panels** | Each query creates a new panel. Toggle between **Table** and **Graph** views within each panel |

**Example questions to try**:
- "What drugs treat atrial fibrillation?"
- "What genes are associated with heart failure?"
- "What pathways involve PCSK9?"
- "What clinical trials study hypertrophic cardiomyopathy?"

---

### Sidebar — Disease Subgraph Extraction

<!-- SCREENSHOT PLACEHOLDER: Capture the left sidebar showing the "Extract
     Disease Subgraph" section with a disease typed in, hop slider set to 2,
     and the export buttons visible. -->

> **[Screenshot: Sidebar with Extract Disease Subgraph controls]**

| What you see | What it means |
|---|---|
| **Disease input** | Type a cardiovascular disease name |
| **Hop slider** (1–3) | How many relationship steps to traverse from the disease |
| **Build Subgraph** | Extracts all entities and relationships within N hops |
| **Export JSON / Export CSV** | Download the extracted subgraph for offline analysis |

**Use case**: Bulk data export for computational analysis in Python, R, or Excel.

---

## Color Legend

| Node Color | Entity Type | Example |
|---|---|---|
| Red | Disease | Atrial fibrillation |
| Blue | Gene | PCSK9, SCN5A |
| Green | Drug | Amiodarone, Warfarin |
| Orange | Pathway | Cardiac conduction |
| Purple | Phenotype | Tachycardia |
| Pink | Variant | rs12345 |
| Teal | Clinical Trial | NCT01234567 |
| Gray | Other types | Body part, symptom, etc. |

*Exact colors may vary slightly. Refer to the on-screen legend for the current session.*

---

## Key Things to Know

1. **All solid edges come from curated databases** (e.g., DrugBank, ClinVar, OpenTargets). Click any edge to see which database it came from.

2. **Cyan dashed edges are ML predictions**, not established facts. They represent computationally predicted drug–disease links (RotatE and CompGCN + XGBoost models, AUROC > 0.96). Each prediction includes a confidence score. These are research hypotheses, not clinical recommendations.

3. **The graph integrates 23 data sources** — you don't need to query them individually. Sources include ClinicalTrials.gov, DrugBank, ClinVar, OpenTargets, STRING, Reactome, HPO, and more.

4. **Natural language queries** are translated to database queries by an AI model. If a query doesn't return what you expect, try rephrasing or use the Cypher input for precise control.

---

## Need Help?

- Click the **?** icons next to any section for detailed explanations.
- Click the **"How does this work?"** link in the Explore tab for methodology details.
- Contact: **[study coordinator email — to be filled in]**
