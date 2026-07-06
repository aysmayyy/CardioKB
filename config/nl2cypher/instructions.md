Instructions:
- Only output a valid Cypher query. Do not include explanations, markdown, or extra text. **Do not use triple backticks or code fences.**
- You must use **every preferred display property** listed in PREFERRED_PROPS_JSON for each node label in the WHERE clause.
- Use only the labels, relationships, and properties present in SCHEMA_JSON and TOPOLOGY_JSON. Do not invent or use fields not listed there.
- When filtering text:
  - Use `toLower(property) CONTAINS toLower("text")` for partial matches.
  - IMPORTANT: CONTAINS is a substring match — the search term must appear verbatim inside the stored value. Clinicians use natural language that may not match stored names exactly. To maximize recall, truncate search terms to their shortest unambiguous stem. Examples:
    - User says "QT prolongation" → use `CONTAINS "qt prolong"` (matches "Electrocardiogram QT prolonged")
    - User says "hypertensive" → use `CONTAINS "hypertens"` (matches "hypertension", "hypertensive")
    - User says "cardiac arrest" → use `CONTAINS "cardiac arrest"` (already a good substring)
    - User says "blood pressure" → use `CONTAINS "blood pressure"` but ALSO try `CONTAINS "hypertens"` with OR since clinicians may mean "hypertension"
  - Common medical synonyms that differ from stored values — use these mappings in CONTAINS:
    - "beta blocker" → search for "adrenergic beta" (stored as "Adrenergic beta-Antagonists")
    - "calcium channel blocker" → search for "calcium channel block" (stored as "Calcium Channel Blockers")
    - "ACE inhibitor" → search for "angiotensin-converting enzyme inhib" (stored as "Angiotensin-converting Enzyme Inhibitors")
    - "statin" → search for "hmg-coa" OR "statin" (stored as "HMG-CoA Reductase Inhibitors")
    - "blood thinner" / "anticoagulant" → search for "anticoagul"
    - "high blood pressure" → search for "hypertens"
    - "heart attack" → search for "myocardial infarction"
    - "blood clot" → search for "thromb"
  - Use `property = toLower("value")` for exact matches **only** when the user clearly asks for a specific identifier. But you must still use **all** preferred properties for that label. Join predicates with `OR`.
- When a label lists multiple preferred properties (e.g., `prop1 or prop2`), include **all** of them in the WHERE clause joined with `OR` (both for partial and exact matches).
- CRITICAL: Always write relationships as UNDIRECTED (no arrows):
  `MATCH (a:Label)-[:relationshipName]-(b:Label)`
  NEVER use `->` or `<-` arrows in any MATCH clause. The graph has mixed edge directions and directed queries will silently return empty results.
- Avoid using internal IDs unless explicitly requested.
- Avoid unnecessary filters like `IS NOT NULL`.
- Use multiple MATCH clauses when querying through multiple relationships (multi-hop traversal). CRITICAL: multi-hop queries create cartesian products (duplicate rows) when intermediate nodes fan out. To prevent this, use `WITH DISTINCT` between MATCH clauses to deduplicate intermediate results before the next hop. Example:
  MATCH (g:Gene)-[:geneAssociatesWithDisease]-(d:Disease)
  WHERE toLower(d.diseaseName) CONTAINS toLower("atrial fibrillation")
  WITH DISTINCT g
  MATCH (g)-[:geneInPathway]-(p:Pathway)
  RETURN DISTINCT p.pathwayName
  Without the `WITH DISTINCT g`, each gene appears once per disease match, multiplying all downstream results.
- Use DISTINCT in the RETURN clause to avoid duplicates. When returning drug names, use `toLower(drug.commonName) AS drug` to deduplicate case variants (e.g., "Esmolol" and "esmolol" are the same drug from different sources).
- Use COUNT(DISTINCT ...) when the question asks for "how many", "number of", or "count".
- Always prefer the **preferred display property** listed in PREFERRED_PROPS_JSON in both WHERE and RETURN clauses.
- Use consistent variable names and proper Cypher syntax.
- Ensure all Cypher clauses are ordered correctly: MATCH -> WHERE -> RETURN.
- Be precise and include **all applicable preferred properties** listed in PREFERRED_PROPS_JSON for each label used in the query.
- Add LIMIT 100 to all queries unless the user requests a specific number of results or the query uses COUNT/aggregation.
- IMPORTANT: Medical conditions may be stored as Disease, Phenotype, SideEffect, or Symptom nodes depending on the ontology source. When the user asks about a condition (e.g., "ventricular tachycardia", "headache", "edema"), first check TOPOLOGY_JSON to see which node types connect via the requested relationship. If the condition could plausibly be a Phenotype or SideEffect rather than a Disease, use UNION or multiple MATCH clauses to search across the relevant node types. For example, if asking "what genes are associated with ventricular tachycardia", try both Disease (via geneAssociatesWithDisease) and Phenotype (via geneAssociatesWithPhenotype).
- When a query returns through one relationship type but not another, prefer using UNION ALL to combine results from different node types rather than returning empty results.
- When using UNION or UNION ALL, all branches must return the **exact same column names** using AS aliases. For example: `RETURN g.geneSymbol AS gene, d.diseaseName AS condition` in both branches.
- When the user asks "what drugs treat X", search both drugTreatsDisease (Drug→Disease) and drugTreatsPhenotype (Drug→Phenotype) since many conditions like tachycardia exist only as Phenotype nodes.
- For a SINGLE condition, use UNION ALL with two branches (one per relationship type).
- For MULTIPLE conditions (e.g., "drugs treating both X and Y"), do NOT use 4-branch UNION ALL — it creates extremely slow cartesian products. Instead, use OPTIONAL MATCH + WITH filtering:
  MATCH (drug:Drug)
  OPTIONAL MATCH (drug)-[:drugTreatsDisease]-(d1:Disease) WHERE toLower(d1.diseaseName) CONTAINS toLower("atrial fibrillation")
  OPTIONAL MATCH (drug)-[:drugTreatsPhenotype]-(p1:Phenotype) WHERE toLower(p1.phenotypeName) CONTAINS toLower("atrial fibrillation")
  WITH drug WHERE d1 IS NOT NULL OR p1 IS NOT NULL
  OPTIONAL MATCH (drug)-[:drugTreatsDisease]-(d2:Disease) WHERE toLower(d2.diseaseName) CONTAINS toLower("tachycardia")
  OPTIONAL MATCH (drug)-[:drugTreatsPhenotype]-(p2:Phenotype) WHERE toLower(p2.phenotypeName) CONTAINS toLower("tachycardia")
  WITH drug WHERE d2 IS NOT NULL OR p2 IS NOT NULL
  RETURN DISTINCT toLower(drug.commonName) AS drug LIMIT 100
- ClinicalTrial phase values are stored WITHOUT spaces: "PHASE1", "PHASE2", "PHASE3", "PHASE4", "PHASE1|PHASE2", "PHASE2|PHASE3", "EARLY_PHASE1", "NA". When the user says "Phase 3", filter with `toLower(ct.phase) CONTAINS "phase3"` (no space). Never use "phase 3" with a space.
- ClinicalTrial status values: "RECRUITING", "COMPLETED", "TERMINATED", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "WITHDRAWN", "UNKNOWN". Only filter on status if the user explicitly asks for it (e.g., "currently recruiting"). Do not assume "currently" means "recruiting" — it may just mean the trial exists.
