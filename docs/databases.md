
# CardioKB Data Sources

## Summary
- **23 databases** — 23 parsers, all working, deduplicated (one authoritative source per node/edge type)
- **4,891,227 nodes** | **7,682,399 relationships** | **17 node types** | **40 relationship types** | **20 source labels**
- **2 legacy sources** retained as-is: SIDER (2015), LINCS L1000 (2020) — no live API alternatives available

## Direct Parsers (5)

| # | Database | Access Type | Parser Status | Notes |
|---|----------|-------------|---------------|-------|
| 1 | ClinicalTrials.gov | Public API v2 | Working | 85,691 trials, 27,866 STUDIES_CONDITION + 17,492 TESTS_INTERVENTION edges |
| 2 | ClinPGx (PharmGKB successor) | Public API | Working | 1,091 VARIANT_IN, 503 drugLabelAnnotatesGene, 345 drugLabelDescribesDrug, 243 AFFECTS_RESPONSE_TO edges |
| 3 | NCBI Gene | Public FTP | Working | 194,553 genes, 26,417 geneInSpecies edges |
| 4 | DoRothEA (OmniPath) | Public API | Working | 12,985 TF-gene interactions with morScore + confidence |
| 5 | DrugBank | XML file | Working | 19,842 drugs + 4,572 CTD unique Drug nodes, 12,089 drugBindsGene edges |

## Hetionet-Derived Component Parsers (16)

| # | Database | Access Type | Parser Status | Notes |
|---|----------|-------------|---------------|-------|
| 6 | Disease Ontology (DOID) | Public | Working | 12,012 diseases, 258 diseaseIsSubtypeOf edges |
| 7 | Gene Ontology (GO) | Public | Working | 50,350 BP + 26,935 MF + 25,794 CC edges |
| 8 | Uberon (anatomy) | Public | Working | 14,937 anatomy nodes (nodes only) |
| 9 | NCBI MeSH (symptoms) | Public | Working | 966 symptom nodes (nodes only) |
| 10 | SIDER (side effects) | Public | Working | 5,734 side effects, 148,518 compoundCausesSideEffect edges. **Legacy: pinned to 2015 GitHub commit; retained — no live API alternative** |
| 11 | LINCS L1000 (gene expression) | Public | Working | 150,540 geneRegulatesGene + 10,218 compoundDownregulatesGene + 10,278 compoundUpregulatesGene edges with zScore. **Legacy: pinned to 2020 GitHub commit; retained — clue.io API requires institutional access** |
| ~~12~~ | ~~MEDLINE (literature cooccurrence)~~ | ~~Public~~ | ~~Removed~~ | ~~365 total edges~~ — **Removed: minimal value (365 edges), anatomy/symptom cooccurrence too sparse for ML** |
| 13 | DrugCentral (drug-disease) | Public | Working | 16,403 pharmacologicClassIncludesCompound + 16,403 compoundInPharmacologicClass + 245 drugTreatsDisease + 96 drugPalliatesDisease edges (CUI-to-DOID mapped) |
| 14 | BindingDB (drug-target) | Public | Working | 12,250 chemicalBindsGene edges |
| 15 | PubTator Central (literature mining) | Public FTP | Working | 673,374 geneAssociatesWithDisease + 4,320 diseaseAssociatesWithDisease edges (after CVD AND-filter) |
| 16 | CTD (chemical-gene) | Public | Working | 4,572 unique Drug nodes (merged with DrugBank where overlapping), 116,451 chemicalIncreasesExpression + 97,951 chemicalDecreasesExpression edges |
| 17 | Bgee (gene expression) | Public FTP | Working | 784,026 bodyPartUnderexpressesGene + 1,872 bodyPartOverexpressesGene edges with expressionScore |
| 18 | Jensen TISSUES (gene-tissue) | Public | Working | 215,235 geneExpressedInBodyPart edges |
| 19 | HPO (Human Phenotype Ontology) | Public | Working | 19,389 phenotypes, 162,994 geneAssociatesWithPhenotype edges |
| 20 | Reactome | Public | Working | 44,979 geneInPathway + 44,979 pathwayContainsGene edges |
| 21 | STRING | Public | Working | 121,170 geneInteractsWithGene edges (confidence > 700) |
| 22 | OpenTargets | Public | Working | 103,879 geneAssociatesWithDisease edges (after CVD AND-filter, via EFO-to-DOID mapping) |

## Agent-Generated Parsers (2)

| # | Database | Access Type | Parser Status | Notes |
|---|----------|-------------|---------------|-------|
| 21 | HGNC Gene Families | Public | Working | 1,934 GeneFamily nodes, 5,123 geneInFamily + 5,123 familyContainsGene edges |
| 22 | ClinVar | Public FTP | Working | 4,488,042 Variant nodes, 2,267,095 hasVariant + 2,267,095 variantInGene + 99,707 associatedWithVariant + 99,707 variantAssociatedWithDisease edges |

## Sources Removed During Deduplication (13)

| Removed Source | Was Providing | Replaced By | Rationale |
|---------------|---------------|-------------|-----------|
| DisGeNET | 20K gene-disease edges | OpenTargets | OpenTargets has curated evidence scores |
| GWAS Catalog | 45K gene-disease edges | OpenTargets | OpenTargets already ingests GWAS Catalog |
| Jensen DISEASES | 20K gene-disease edges | OpenTargets | Covered by OpenTargets text-mining with better scoring |
| OMIM | 7.3K gene-disease edges | OpenTargets | OpenTargets includes genetic evidence; OMIM gene data retained in CVD gene ontology |
| WikiPathways | 8.6K pathway edges | Reactome | Reactome is gold-standard curated; many WikiPathways imported from Reactome |
| AOP-DB | 18.5K pathway edges | Reactome | AOP-DB focuses on toxicology, less relevant for CVD |
| HGNC (base) | Gene node enrichment | NCBI Gene | NCBI Gene is primary gene reference with daily updates |
| CellAge | Senescence gene nodes | NCBI Gene | Node-only source, genes already in NCBI Gene |
| GenAge | Aging gene nodes | NCBI Gene | Node-only source, genes already in NCBI Gene |
| Hetionet (precomputed) | 138K side effects + 5K PPI + 127 covariance | SIDER + STRING | Side effects covered by SIDER, PPI by STRING; covariance dropped (127 edges) |
| **DrugAge** | 386 associatedWithAging edges, 3 AgeingProperty nodes | — | **Too sparse (386 edges) for ML applications; minimal analytical value** |
| **AnAge** | 4,645 Species nodes | — | **Node-only source with no edges; hurts ML model training** |
| **MEDLINE** | 365 cooccurrence edges (anatomy/symptom/disease) | — | **Too sparse (365 edges); minimal value vs. maintenance cost** |

## Sources Modified During Deduplication (2)

| Source | Change | Reason |
|--------|--------|--------|
| PubTator Central | Kept geneAssociatesWithDisease (literature-mined, complementary to OpenTargets curated) + diseaseAssociatesWithDisease (unique). CVD AND-filter applied to scope results. | PubTator provides literature cooccurrence evidence distinct from OpenTargets curated associations |
| ClinPGx | Removed Variant from node contribution. Kept DrugLabel nodes and all 4 unique edge types. | ClinVar is primary Variant source (4.5M vs 1.1K) |

## Relationship Source Labels (20)

All relationships carry a `source` property identifying the originating database:

`Bgee`, `BindingDB`, `CTD`, `ClinPGx`, `ClinVar`, `ClinicalTrials.gov`, `Disease Ontology`, `DoRothEA`, `DrugBank`, `DrugCentral`, `Gene Ontology`, `HGNC`, `HPO`, `Jensen TISSUES`, `LINCS L1000`, `OpenTargets`, `PubTator`, `Reactome`, `SIDER`, `STRING`

HGNC Families uses `HGNC` as its source label. Disease Ontology contributes relationship source labels (diseaseIsSubtypeOf).
