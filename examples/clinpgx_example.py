"""
Example script demonstrating the ClinPGxParser for pharmacogenomics data.

This script shows how to:
1. Query ClinPGx API for cardiovascular pharmacogenomics data
2. Parse gene-drug pairs, guidelines, annotations, labels, and variants
3. Filter for high-evidence annotations
4. Display summary statistics
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers import ClinPGxParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Main execution function."""

    logger.info("=" * 70)
    logger.info("ClinPGx Pharmacogenomics Parser Example")
    logger.info("=" * 70)

    # Initialize with default CVD pharmacogenes and drugs
    parser = ClinPGxParser(use_cache=True)

    # Download data from API
    logger.info("\n1. Downloading pharmacogenomics data from ClinPGx...")
    success = parser.download_data()

    if not success:
        logger.error("Failed to download data. Exiting.")
        return

    # Parse data
    logger.info("\n2. Parsing data into DataFrames...")
    data = parser.parse_data()

    # Display summaries for each DataFrame
    for key, df in data.items():
        logger.info(f"\n{'=' * 50}")
        logger.info(f"{key}: {len(df)} rows")
        logger.info(f"Columns: {list(df.columns)}")

        if len(df) > 0:
            logger.info(f"\nSample rows:")
            logger.info(df.head(3).to_string(index=False))

    # Filter for high-evidence annotations
    annotations_df = data.get('clinical_annotations')
    if annotations_df is not None and len(annotations_df) > 0:
        logger.info("\n\n3. High-evidence clinical annotations (1A, 1B):")
        logger.info("-" * 50)

        high_evidence = annotations_df[
            annotations_df['evidence_level'].isin(['1A', '1B'])
        ]
        if len(high_evidence) > 0:
            logger.info(f"Found {len(high_evidence)} high-evidence annotations")
            for _, row in high_evidence.head(10).iterrows():
                logger.info(
                    f"  {row['gene']} - {row['drug']}: "
                    f"Level {row['evidence_level']}"
                )
        else:
            logger.info("No high-evidence annotations found in this dataset")

    # Gene-drug pair summary
    gdp_df = data.get('gene_drug_pairs')
    if gdp_df is not None and len(gdp_df) > 0:
        logger.info("\n\n4. Gene-drug pair summary:")
        logger.info("-" * 50)

        logger.info(f"\nUnique genes: {gdp_df['gene'].nunique()}")
        logger.info(f"Unique drugs: {gdp_df['drug'].nunique()}")

        logger.info("\nPairs per gene:")
        for gene, count in gdp_df['gene'].value_counts().head(10).items():
            logger.info(f"  {gene}: {count} drug interactions")

    # Save results
    output_dir = Path(__file__).parent
    for key, df in data.items():
        if len(df) > 0:
            output_file = output_dir / f'clinpgx_{key}.csv'
            df.to_csv(output_file, index=False)
            logger.info(f"\nSaved {key} to: {output_file}")

    logger.info("\n" + "=" * 70)
    logger.info("Example completed!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
