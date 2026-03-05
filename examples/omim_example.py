"""
Example script demonstrating the OMIMParser for genetic disease data.

This script shows how to:
1. Parse OMIM bulk files (genemap2.txt, morbidmap.txt)
2. Extract gene-disease relationships
3. Filter for cardiovascular genetic conditions
4. Display CVD-related genes and inheritance patterns

Note: Requires genemap2.txt and morbidmap.txt in the data directory,
or an OMIM_API_KEY in .env to download them automatically.
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers import OMIMParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Main execution function."""

    logger.info("=" * 70)
    logger.info("OMIM Genetic Disease Parser Example")
    logger.info("=" * 70)

    # Initialize parser
    # API key is read from OMIM_API_KEY env var if available
    parser = OMIMParser()

    # Download/locate data files
    logger.info("\n1. Locating OMIM data files...")
    success = parser.download_data()

    if not success:
        logger.error(
            "OMIM data files not found. Either:\n"
            "  - Set OMIM_API_KEY in your .env file, or\n"
            "  - Place genemap2.txt and morbidmap.txt in:\n"
            f"    {parser.source_dir}/"
        )
        return

    # Parse data
    logger.info("\n2. Parsing OMIM data...")
    data = parser.parse_data()

    # Gene-phenotype map summary
    genemap_df = data.get('gene_phenotype_map')
    if genemap_df is not None and len(genemap_df) > 0:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"Gene-Phenotype Map: {len(genemap_df)} entries")
        logger.info(f"Genes with symbols: {genemap_df['gene_symbol'].notna().sum()}")
        logger.info(f"Genes with phenotypes: {(genemap_df['phenotypes_raw'].str.len() > 0).sum()}")

    # Gene-disease relationships summary
    gdr_df = data.get('gene_disease_relationships')
    if gdr_df is not None and len(gdr_df) > 0:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"Gene-Disease Relationships: {len(gdr_df)} entries")

        cvd_count = gdr_df['is_cvd'].sum()
        logger.info(f"CVD-related: {cvd_count} ({100 * cvd_count / len(gdr_df):.1f}%)")

        logger.info("\nMapping key distribution:")
        for key, count in gdr_df['mapping_key'].value_counts().sort_index().items():
            labels = {
                '1': 'gene with known sequence and phenotype',
                '2': 'gene with known sequence',
                '3': 'phenotype mapped to chromosomal location',
                '4': 'deletion/duplication syndrome'
            }
            label = labels.get(str(key), 'unknown')
            logger.info(f"  Key {key} ({label}): {count}")

    # CVD genes summary
    cvd_genes_df = data.get('omim_cvd_genes')
    if cvd_genes_df is not None and len(cvd_genes_df) > 0:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"CVD-Related Genes: {len(cvd_genes_df)}")

        logger.info("\nTop 20 CVD genes (by phenotype count):")
        for _, row in cvd_genes_df.head(20).iterrows():
            logger.info(
                f"  {row['gene_symbol']}: "
                f"{row['cvd_phenotype_count']} phenotypes"
            )
            phenotypes = row['cvd_phenotypes']
            if phenotypes:
                for p in phenotypes.split('; ')[:3]:
                    logger.info(f"    - {p[:70]}")

        # Inheritance pattern distribution
        all_patterns = []
        for patterns in cvd_genes_df['inheritance_patterns'].dropna():
            if patterns:
                all_patterns.extend(
                    p.strip() for p in patterns.split(';') if p.strip()
                )

        if all_patterns:
            logger.info("\nInheritance patterns in CVD genes:")
            from collections import Counter
            for pattern, count in Counter(all_patterns).most_common():
                logger.info(f"  {pattern}: {count}")

    # Save results
    output_dir = Path(__file__).parent
    for key, df in data.items():
        if len(df) > 0:
            output_file = output_dir / f'omim_{key}.csv'
            df.to_csv(output_file, index=False)
            logger.info(f"\nSaved {key} to: {output_file}")

    logger.info("\n" + "=" * 70)
    logger.info("Example completed!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
