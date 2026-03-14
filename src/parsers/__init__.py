"""
Data parsers for CardioKB.

This module contains parsers for various data sources used to populate CardioKB.
Each parser is responsible for downloading, parsing, and formatting data from
a specific source.

Custom parsers (CardioKB-specific):
  - ClinicalTrialsParser: ClinicalTrials.gov API v2
  - ClinPGxParser: ClinPGx pharmacogenomics
  - OMIMParser: OMIM genetic disorders

Base KB parsers (adapted from AlzKB):
  - NCBIGeneParser: NCBI Gene (disease-agnostic)
  - DrugBankParser: DrugBank (disease-agnostic)
  - AOPDBParser: AOP-DB MySQL (disease-agnostic)
  - DoRothEAParser: DoRothEA TF network (disease-agnostic)
  - DisGeNETParser: DisGeNET gene-disease associations (CVD-scoped)
  - JensenLabParser: Jensen Lab DISEASES gene-disease associations

Hetionet component parsers (disease-agnostic):
  - DiseaseOntologyParser: Disease Ontology (DOID) nodes
  - GeneOntologyParser: GO BP/MF/CC nodes + gene-GO edges
  - UberonParser: Anatomy/BodyPart nodes (UBERON)
  - MeSHParser: Symptom nodes (MeSH)
  - SIDERParser: SideEffect nodes + compound-causes-sideEffect edges
  - LINCS1000Parser: LINCS L1000 expression edges (CuG, CdG, GrG)
  - MEDLINECooccurrenceParser: MEDLINE co-occurrence edges (DpS, DlA, DrD)
  - DrugCentralParser: Drug-treats/palliates, PharmClass nodes, PCiC edges
  - GWASParser: Gene-disease association edges
  - PubTatorParser: Literature-mined co-occurrences
  - BindingDBParser: chemicalBindsGene edges
  - CTDParser: chemicalIncreases/DecreasesExpression edges
  - BgeeParser: bodyPartOver/UnderexpressesGene edges
  - HetionetPrecomputedParser: Gene-gene relationship edges
"""

from .base_parser import BaseParser
from .clinicaltrials_parser import ClinicalTrialsParser
from .clinpgx_parser import ClinPGxParser
from .omim_parser import OMIMParser
from .ncbigene_parser import NCBIGeneParser
from .drugbank_parser import DrugBankParser
from .aopdb_parser import AOPDBParser
from .dorothea_parser import DoRothEAParser
from .disgenet_parser import DisGeNETParser
from .jensenlab_parser import JensenLabParser
from .hetionet_components import (
    DiseaseOntologyParser,
    GeneOntologyParser,
    UberonParser,
    MeSHParser,
    GWASParser,
    DrugCentralParser,
    BindingDBParser,
    BgeeParser,
    CTDParser,
    HetionetPrecomputedParser,
    PubTatorParser,
    SIDERParser,
    LINCS1000Parser,
    MEDLINECooccurrenceParser,
)

__all__ = [
    'BaseParser',
    # Custom parsers
    'ClinicalTrialsParser',
    'ClinPGxParser',
    'OMIMParser',
    # Base KB parsers
    'NCBIGeneParser',
    'DrugBankParser',
    'AOPDBParser',
    'DoRothEAParser',
    'DisGeNETParser',
    # Hetionet component parsers
    'DiseaseOntologyParser',
    'GeneOntologyParser',
    'UberonParser',
    'MeSHParser',
    'GWASParser',
    'DrugCentralParser',
    'BindingDBParser',
    'BgeeParser',
    'CTDParser',
    'HetionetPrecomputedParser',
    'PubTatorParser',
    'SIDERParser',
    'LINCS1000Parser',
    'MEDLINECooccurrenceParser',
    'JensenLabParser',
]
