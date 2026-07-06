# Examples

## disease_example
MATCH (d:Disease)
WHERE toLower(d.{{DISEASE_PROP}}) CONTAINS toLower("diabetes")
RETURN DISTINCT d.{{DISEASE_PROP}}
LIMIT 100

## gene_example
MATCH (g:Gene)
WHERE {{GENE_WHERE}}
RETURN DISTINCT {{GENE_RETURN}}
LIMIT 100

## pathway_example
MATCH (p:Pathway)
WHERE toLower(p.pathwayName) CONTAINS toLower("calcium signaling")
RETURN DISTINCT p.pathwayName
LIMIT 100

## multi_entity_join_example
MATCH (d:Drug)-[:chemicalBindsGene]-(g:Gene)
WHERE toLower(d.commonName) CONTAINS toLower("aspirin")
MATCH (g)-[:geneAssociatesWithDisease]-(ds:Disease)
WHERE toLower(ds.diseaseName) CONTAINS toLower("atrial fibrillation")
RETURN DISTINCT g.geneSymbol, ds.diseaseName
LIMIT 100

## multihop_example
MATCH (g:Gene)-[:geneAssociatesWithDisease]-(d:Disease)
WHERE toLower(d.diseaseName) CONTAINS toLower("heart failure")
WITH DISTINCT g
MATCH (g)-[:geneHasMolecularFunction]-(mf:MolecularFunction)
RETURN DISTINCT mf.functionName
LIMIT 100

## multihop_clinical_trial_example
MATCH (g:Gene)-[:geneAssociatesWithDisease]-(d:Disease)
WHERE toLower(d.diseaseName) CONTAINS toLower("atrial fibrillation")
WITH DISTINCT g
MATCH (d2:Drug)-[:drugBindsGene]-(g)
WITH DISTINCT d2
MATCH (ct:ClinicalTrial)-[:TESTS_INTERVENTION]-(d2)
RETURN DISTINCT d2.commonName AS drug, ct.title AS trial, ct.phase AS phase, ct.status AS status
LIMIT 100

## count_example
MATCH (g:Gene)-[:geneAssociatesWithDisease]-(d:Disease)
WHERE toLower(d.diseaseName) CONTAINS toLower("atrial fibrillation")
RETURN COUNT(DISTINCT g) AS geneCount

## exact_lookup_example
MATCH (g:Gene)
WHERE toLower(g.geneSymbol) = toLower("APOE")
RETURN DISTINCT g.geneSymbol, g.geneId, g.description
LIMIT 100

## drug_treats_disease_example
MATCH (d:Drug)-[:drugTreatsDisease]-(ds:Disease)
WHERE toLower(ds.diseaseName) CONTAINS toLower("hypertension")
RETURN DISTINCT d.commonName, ds.diseaseName
LIMIT 100

## gene_pathway_example
MATCH (g:Gene)-[:geneAssociatesWithDisease]-(d:Disease)
WHERE toLower(d.diseaseName) CONTAINS toLower("coronary artery disease")
MATCH (g)-[:geneInPathway]-(p:Pathway)
RETURN DISTINCT p.pathwayName, g.geneSymbol
LIMIT 100

## variant_disease_example
MATCH (v:Variant)-[:variantAssociatedWithDisease]-(d:Disease)
WHERE toLower(d.diseaseName) CONTAINS toLower("cardiomyopathy")
RETURN DISTINCT v.variantName, v.clinicalSignificance, d.diseaseName
LIMIT 100

## side_effect_example
MATCH (d:Drug)-[:compoundCausesSideEffect]-(se:SideEffect)
WHERE toLower(d.commonName) CONTAINS toLower("metoprolol")
RETURN DISTINCT se.sideEffectName
LIMIT 100

## clinical_trial_example
MATCH (ct:ClinicalTrial)-[:STUDIES_CONDITION]-(d:Disease)
WHERE toLower(d.diseaseName) CONTAINS toLower("atrial fibrillation")
RETURN DISTINCT ct.title, ct.phase, ct.status
LIMIT 100

## drug_class_treats_disease_example
MATCH (d:Drug)-[:compoundInPharmacologicClass]-(pc:PharmacologicClass)
WHERE toLower(pc.className) CONTAINS toLower("anticoagul")
WITH DISTINCT d
MATCH (d)-[:drugTreatsDisease]-(ds:Disease)
WHERE toLower(ds.diseaseName) CONTAINS toLower("atrial fibrillation")
RETURN DISTINCT toLower(d.commonName) AS drug, ds.diseaseName AS disease
LIMIT 100

## pharmacogenomics_example
MATCH (dl:DrugLabel)-[:drugLabelDescribesDrug]-(d:Drug)
WHERE toLower(d.commonName) CONTAINS toLower("warfarin")
MATCH (dl)-[:drugLabelAnnotatesGene]-(g:Gene)
RETURN DISTINCT g.geneSymbol AS gene, dl.labelName AS label
LIMIT 100

## cross_type_condition_example
MATCH (g:Gene)-[:geneAssociatesWithDisease]-(d:Disease)
WHERE toLower(d.diseaseName) CONTAINS toLower("ventricular tachycardia")
RETURN DISTINCT g.geneSymbol AS gene, d.diseaseName AS condition, "Disease" AS sourceType
UNION ALL
MATCH (g:Gene)-[:geneAssociatesWithPhenotype]-(p:Phenotype)
WHERE toLower(p.phenotypeName) CONTAINS toLower("ventricular tachycardia")
RETURN DISTINCT g.geneSymbol AS gene, p.phenotypeName AS condition, "Phenotype" AS sourceType

## drug_treats_condition_union_example
MATCH (d:Drug)-[:drugTreatsDisease]-(ds:Disease)
WHERE toLower(ds.diseaseName) CONTAINS toLower("tachycardia")
RETURN DISTINCT toLower(d.commonName) AS drug, ds.diseaseName AS condition, "Disease" AS sourceType
UNION ALL
MATCH (d:Drug)-[:drugTreatsPhenotype]-(p:Phenotype)
WHERE toLower(p.phenotypeName) CONTAINS toLower("tachycardia")
RETURN DISTINCT toLower(d.commonName) AS drug, p.phenotypeName AS condition, "Phenotype" AS sourceType
