"""
ClinVarParser: Parser for ClinVar variant database.

Downloads the ClinVar variant summary file and produces:
- Variant nodes with genomic coordinates and clinical significance
- Gene-variant relationships
- Disease-variant relationships via phenotypes
- Variant properties for clinical impact assessment

Source: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz
Access: Public (no credentials required)
License: Public domain (NCBI)
"""

import logging
from typing import Dict, Optional

import pandas as pd

from .base_parser import BaseParser

logger = logging.getLogger(__name__)

# Column names with '#' prefix must be stored as constants
ALLELE_ID_COL = '#AlleleID'
RS_DBSNP_COL = 'RS# (dbSNP)'
NSV_DBVAR_COL = 'nsv/esv (dbVar)'


class ClinVarParser(BaseParser):
    """Parser for ClinVar variant data."""

    DOWNLOAD_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
    FILENAME = "variant_summary.txt.gz"
    EXTRACTED_FILENAME = "variant_summary.txt"

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)

    def download_data(self) -> bool:
        """Download ClinVar variant summary file."""
        logger.info("Downloading ClinVar data...")
        result = self.download_file(self.DOWNLOAD_URL, self.FILENAME)
        if result is None:
            return False

        # Extract the gzipped file
        extracted = self.extract_gzip(result)
        return extracted is not None

    def parse_data(self) -> Dict[str, pd.DataFrame]:
        """Parse ClinVar data into variant nodes, relationships, and properties."""
        filepath = self.source_dir / self.EXTRACTED_FILENAME
        if not filepath.exists():
            logger.error(f"ClinVar file not found: {filepath}")
            return {}

        # Read TSV file
        df = self.read_tsv(str(filepath))
        if df is None or len(df) == 0:
            logger.error("Failed to read ClinVar data")
            return {}

        logger.info(f"ClinVar raw: {len(df)} rows")

        # Remove rows with missing critical fields
        df_clean = df[df[ALLELE_ID_COL].notna() & df['GeneID'].notna()].copy()
        logger.info(f"ClinVar after filtering: {len(df_clean)} rows")

        # ======== VARIANT NODES ========
        # Create variant nodes with genomic coordinates
        variant_nodes = df_clean[[
            ALLELE_ID_COL, 'Type', 'Name', 'Chromosome', 'Start', 'Stop',
            'ReferenceAllele', 'AlternateAllele', 'ClinicalSignificance',
            'ClinSigSimple', 'Assembly', 'ReviewStatus', 'NumberSubmitters'
        ]].drop_duplicates(subset=[ALLELE_ID_COL]).copy()

        variant_nodes = variant_nodes.rename(columns={
            ALLELE_ID_COL: 'variantId',
            'Type': 'variantType',
            'Name': 'hgvsNomenclature',
            'Chromosome': 'chromosome',
            'Start': 'positionStart',
            'Stop': 'positionStop',
            'ReferenceAllele': 'referenceAllele',
            'AlternateAllele': 'alternateAllele',
            'ClinicalSignificance': 'clinicalSignificance',
            'ClinSigSimple': 'clinicalSignificanceSimple',
            'Assembly': 'genomeAssembly',
            'ReviewStatus': 'reviewStatus',
            'NumberSubmitters': 'numberSubmitters',
        })

        # Ensure variantId is string (IDs must be consistently typed for Neo4j MERGE)
        variant_nodes['variantId'] = variant_nodes['variantId'].astype(str)

        # Add derived genomic position field (chr:start-stop) using vectorized string operations
        variant_nodes = variant_nodes.assign(
            genomicPosition=(
                variant_nodes['chromosome'].astype(str) + ':' +
                variant_nodes['positionStart'].astype(str) + '-' +
                variant_nodes['positionStop'].astype(str)
            ),
            sourceDatabase='ClinVar'
        )

        logger.info(f"ClinVar: {len(variant_nodes)} unique variants")

        # ======== GENE-VARIANT RELATIONSHIPS ========
        # Create gene-variant edges (match Gene on xrefNcbiGene)
        gene_variant = df_clean[[
            'GeneID', 'GeneSymbol', ALLELE_ID_COL, 'ClinicalSignificance'
        ]].dropna(subset=['GeneID']).copy()

        gene_variant = gene_variant.rename(columns={
            'GeneID': 'gene_id',
            ALLELE_ID_COL: 'variant_id',
            'GeneSymbol': 'gene_symbol',
            'ClinicalSignificance': 'clinicalSignificance',
        })

        # Remove duplicates
        gene_variant = gene_variant.drop_duplicates(subset=['gene_id', 'variant_id'])
        logger.info(f"ClinVar: {len(gene_variant)} gene-variant relationships")

        # ======== DISEASE-VARIANT RELATIONSHIPS VIA PHENOTYPES ========
        # Parse PhenotypeIDS using vectorized string operations
        # Format: "MONDO:MONDO:0013342,MedGen:C3150901,OMIM:613647,Orphanet:306511||MedGen:C3661900"

        phenotype_work = df_clean[[
            ALLELE_ID_COL, 'PhenotypeIDS', 'PhenotypeList'
        ]].copy()

        # Filter to rows with valid phenotype IDs
        phenotype_work = phenotype_work[
            (phenotype_work['PhenotypeIDS'].notna()) &
            (phenotype_work['PhenotypeIDS'] != '-') &
            (phenotype_work['PhenotypeIDS'] != '')
        ].copy()

        if len(phenotype_work) > 0:
            # Split PhenotypeIDS by '||' to get individual phenotype groups
            phenotype_work = phenotype_work.rename(columns={
                ALLELE_ID_COL: 'variant_id'
            })

            # Explode by phenotype groups (split on '||')
            phenotype_work['phenotype_group'] = phenotype_work['PhenotypeIDS'].str.split(r'\|\|')
            phenotype_work = phenotype_work.explode('phenotype_group').reset_index(drop=True)

            # Split phenotype names on '|' for alignment
            phenotype_work['phenotype_name_list'] = phenotype_work['PhenotypeList'].str.split(r'\|')

            # Get group index for name alignment
            phenotype_work['group_idx'] = phenotype_work.groupby(level=0).cumcount()

            # Extract phenotype names: for each group, get corresponding name
            # This is a bit tricky since we need to align exploded groups with name list
            phenotype_work = phenotype_work.dropna(subset=['phenotype_group'])
            phenotype_work['phenotype_group'] = phenotype_work['phenotype_group'].str.strip()

            # Filter out empty groups
            phenotype_work = phenotype_work[phenotype_work['phenotype_group'] != '']

            # Split IDs within each phenotype group by comma
            phenotype_work['id_list'] = phenotype_work['phenotype_group'].str.split(',')
            phenotype_work = phenotype_work.explode('id_list').reset_index(drop=True)

            phenotype_work['id_list'] = phenotype_work['id_list'].str.strip()
            phenotype_work = phenotype_work[phenotype_work['id_list'] != '']

            # Extract prefix and identifier
            phenotype_work = phenotype_work[phenotype_work['id_list'].str.contains(':', na=False)]

            phenotype_work[['prefix', 'identifier']] = phenotype_work['id_list'].str.split(':', n=1, expand=True)
            phenotype_work['identifier'] = phenotype_work['identifier'].str.strip()
            phenotype_work['prefix'] = phenotype_work['prefix'].str.strip()

            # Build disease IDs for supported ontologies
            phenotype_work = phenotype_work[phenotype_work['prefix'].isin(['OMIM', 'MONDO', 'Orphanet'])]

            phenotype_work = phenotype_work.assign(
                disease_id=phenotype_work['prefix'] + ':' + phenotype_work['identifier'],
                source_ontology=phenotype_work['prefix']
            )

            # Get phenotype names by group index (simplified: use first available or None)
            phenotype_work['phenotype_name'] = phenotype_work.apply(
                lambda row: (
                    row['phenotype_name_list'][row['group_idx']]
                    if isinstance(row['phenotype_name_list'], list) and row['group_idx'] < len(row['phenotype_name_list'])
                    else None
                ),
                axis=1
            )

            disease_variant = phenotype_work[[
                'variant_id', 'disease_id', 'phenotype_name', 'source_ontology'
            ]].drop_duplicates().reset_index(drop=True)

            logger.info(f"ClinVar: {len(disease_variant)} disease-variant relationships")

            # Split by ontology for different matching strategies in Neo4j:
            # - OMIM diseases match on Disease.xrefOMIM (plain number)
            # - MONDO/Orphanet need separate handling
            dv_omim = disease_variant[disease_variant['source_ontology'] == 'OMIM'].copy()
            # Extract plain OMIM number (e.g., "OMIM:613647" → "613647")
            dv_omim['disease_id'] = dv_omim['disease_id'].str.replace('OMIM:', '', regex=False)
            logger.info(f"ClinVar: {len(dv_omim)} OMIM disease-variant relationships")

            dv_mondo = disease_variant[disease_variant['source_ontology'] == 'MONDO'].copy()
            logger.info(f"ClinVar: {len(dv_mondo)} MONDO disease-variant relationships")

            dv_orphanet = disease_variant[disease_variant['source_ontology'] == 'Orphanet'].copy()
            logger.info(f"ClinVar: {len(dv_orphanet)} Orphanet disease-variant relationships")
        else:
            empty_dv = pd.DataFrame(columns=[
                'variant_id', 'disease_id', 'phenotype_name', 'source_ontology'
            ])
            dv_omim = empty_dv.copy()
            dv_mondo = empty_dv.copy()
            dv_orphanet = empty_dv.copy()
            logger.info("ClinVar: 0 disease-variant relationships found")

        # ======== VARIANT PROPERTIES ========
        # Extract clinical impact and somatic information
        variant_properties = df_clean[[
            ALLELE_ID_COL, RS_DBSNP_COL, NSV_DBVAR_COL, 'RCVaccession',
            'LastEvaluated', 'Origin', 'OriginSimple', 'Guidelines',
            'SomaticClinicalImpact', 'SomaticClinicalImpactLastEvaluated',
            'Oncogenicity', 'OncogenicityLastEvaluated'
        ]].drop_duplicates(subset=[ALLELE_ID_COL]).copy()

        variant_properties = variant_properties.rename(columns={
            ALLELE_ID_COL: 'variantId',
            RS_DBSNP_COL: 'dbSnpId',
            NSV_DBVAR_COL: 'dbVarId',
            'RCVaccession': 'rcvAccession',
            'LastEvaluated': 'lastEvaluated',
            'Origin': 'origin',
            'OriginSimple': 'originSimple',
            'Guidelines': 'guidelines',
            'SomaticClinicalImpact': 'somaticClinicalImpact',
            'SomaticClinicalImpactLastEvaluated': 'somaticLastEvaluated',
            'Oncogenicity': 'oncogenicity',
            'OncogenicityLastEvaluated': 'oncogenicityLastEvaluated',
        })

        # Convert '-' to None for cleaner data using vectorized replace
        columns_to_clean = [
            'dbSnpId', 'dbVarId', 'rcvAccession', 'lastEvaluated',
            'origin', 'originSimple', 'guidelines', 'somaticClinicalImpact',
            'somaticLastEvaluated', 'oncogenicity', 'oncogenicityLastEvaluated'
        ]

        for col in columns_to_clean:
            if col in variant_properties.columns:
                variant_properties[col] = variant_properties[col].replace('-', None)

        logger.info(f"ClinVar: {len(variant_properties)} variant property records")

        return {
            'variant_nodes': variant_nodes,
            'gene_variant': gene_variant,
            'disease_variant_omim': dv_omim,
            'disease_variant_mondo': dv_mondo,
            'disease_variant_orphanet': dv_orphanet,
            'variant_properties': variant_properties,
        }

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        return {
            'variant_nodes': {
                'variantId': 'ClinVar AlleleID (primary identifier)',
                'variantType': 'Type of variant (SNV, Indel, Deletion, etc.)',
                'hgvsNomenclature': 'HGVS nomenclature for the variant',
                'chromosome': 'Chromosome number',
                'positionStart': 'Start position on chromosome',
                'positionStop': 'Stop position on chromosome',
                'referenceAllele': 'Reference allele sequence',
                'alternateAllele': 'Alternate allele sequence',
                'clinicalSignificance': 'Clinical significance assessment',
                'clinicalSignificanceSimple': 'Simplified clinical significance (0=uncertain, 1=pathogenic)',
                'genomeAssembly': 'Genome assembly version (GRCh37/GRCh38)',
                'genomicPosition': 'Derived genomic position (chr:start-stop)',
                'reviewStatus': 'ClinVar review status',
                'numberSubmitters': 'Number of submitters',
                'sourceDatabase': 'Source database identifier',
            },
            'gene_variant': {
                'gene_id': 'NCBI Gene ID',
                'variant_id': 'ClinVar AlleleID',
                'gene_symbol': 'Gene symbol',
                'clinicalSignificance': 'Clinical significance for this gene-variant pair',
            },
            'disease_variant': {
                'variant_id': 'ClinVar AlleleID',
                'disease_id': 'Disease identifier (OMIM, MONDO, or Orphanet)',
                'phenotype_name': 'Phenotype/disease name',
                'source_ontology': 'Source ontology (OMIM, MONDO, Orphanet)',
            },
            'variant_properties': {
                'variantId': 'ClinVar AlleleID',
                'dbSnpId': 'dbSNP rs identifier',
                'dbVarId': 'dbVar nsv/esv identifier',
                'rcvAccession': 'RCV accession number',
                'lastEvaluated': 'Last evaluation date',
                'origin': 'Origin of variant',
                'originSimple': 'Simplified origin classification',
                'guidelines': 'Applicable clinical guidelines',
                'somaticClinicalImpact': 'Somatic clinical impact classification',
                'somaticLastEvaluated': 'Last evaluation date for somatic impact',
                'oncogenicity': 'Oncogenicity classification',
                'oncogenicityLastEvaluated': 'Last evaluation date for oncogenicity',
            },
        }