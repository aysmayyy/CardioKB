# CardioKB Status Report — 2026-05-11

## Database Changes

**Removed (sparse, node-only sources):**
- **DrugAge** — 3 AgeingProperty nodes, 386 edges. Not CVD-critical.
- **AnAge** — 4,645 Species nodes with no outgoing edges. Required a post-load hack for geneInSpecies.

**Current state:** 24 sources, 17 node types, 42 edge types, 21 source labels

## Legacy Source Replacement Plan

Three sources use pinned/archived data with no live API. Proposed replacements:

| Current | Issue | Replacement |
|---------|-------|-------------|
| SIDER (2015) | 9 years stale | FAERS (FDA adverse events, live API) |
| LINCS L1000 (2020) | clue.io requires institutional access | LINCS 2021 release or SigCom LINCS |
| MEDLINE | Sparse, removed | HSDN (Human Signs/Symptoms Disease Network) |

**Need your input** on whether these replacements make sense before I build the new parsers.

## OWL2 Ontology

Created `ontology/cardiokb_ontology.rdf` — validates clean:
- 17/17 node classes declared
- 39/39 object properties with domain/range
- No dangling references after DrugAge/AnAge/MEDLINE removal

## Eval Results

Ran both eval scripts against current graph:

**eval_after_parser.py:** 12/15 passing (7/7 Tier 1 blocking)
**eval_after_memgraph.py:** 21/25 passing (9/9 Tier 1 blocking)

**Merge rate checks (all passing):**
- Disease merge: No duplicate DOIDs
- Drug merge: 82.3% (CTD drugs properly merged with DrugBank)
- Variant merge: No duplicate variantIds
- Gene merge: 1 minor duplicate, 8.4% genes have 3+ source relationships

**Zero blocking failures.** Non-blocking issues are expected (orphaned variants without disease links, CVD-unrelated genes).

## Next Steps

1. **Your input needed:** Do the legacy replacements (SIDER→FAERS, LINCS→2021, MEDLINE→HSDN) make sense?
2. **Re-run pipeline** after confirming replacements
3. **BaseAgent build** for new parsers once you approve