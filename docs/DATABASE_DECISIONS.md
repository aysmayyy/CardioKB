# Database Integration Decisions for CardioKB

## Databases to ADD to BaseAgent

### High Priority (Essential):
1. **PharmGKB** - Pharmacogenomics (gene-drug-disease)
2. **ClinicalTrials.gov** - Ongoing/completed clinical trials
3. **OMIM** - Genetic diseases (gold standard)

### Medium Priority (Grant-specified):
4. **FooDB** - Food compounds (grant requirement)
5. **HMDB** - Human metabolites (grant requirement)

### Lower Priority (Optional):
6. **HPO** - Human Phenotype Ontology (if phenotypes needed beyond MeSH)

## Rationale

**PharmGKB:** Fills gap in pharmacogenomics - how genes affect drug response. Not covered by existing sources.

**ClinicalTrials.gov:** Shows investigational/emerging therapeutics. DrugBank only has approved drugs.

**OMIM:** Authoritative source for genetic diseases. Some overlap with DisGeNET but adds inheritance patterns, rare diseases, detailed clinical info. Critical for genetic arrhythmias (Long QT, Brugada, etc.).

**FooDB/HMDB:** Grant specifically requires metabolite and dietary data for CVD research.