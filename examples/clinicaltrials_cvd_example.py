"""
Example script demonstrating the broadened ClinicalTrialsParser for CVD.

This script shows how to:
1. Query ClinicalTrials.gov API for all cardiovascular disease trials (default)
2. Use RNA therapeutics mode
3. Use custom query mode
4. Display summary statistics
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers import ClinicalTrialsParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Main execution function."""

    logger.info("=" * 70)
    logger.info("ClinicalTrials.gov CVD Parser Example")
    logger.info("=" * 70)

    # --- Mode 1: Broad CVD query (default) ---
    logger.info("\n1. BROAD CVD QUERY MODE (default)")
    logger.info("-" * 40)

    parser = ClinicalTrialsParser(
        query_mode="cvd",
        max_results=200  # Limit per category for demo
    )

    success = parser.download_data()
    if not success:
        logger.error("Failed to download CVD data. Exiting.")
        return

    data = parser.parse_data()
    cvd_df = data.get('clinical_trials')

    if cvd_df is not None and len(cvd_df) > 0:
        logger.info(f"\nTotal unique CVD trials: {len(cvd_df)}")

        logger.info("\nTop 10 conditions:")
        for cond, count in cvd_df['condition'].value_counts().head(10).items():
            logger.info(f"  {cond[:70]}: {count}")

        logger.info("\nPhase distribution:")
        for phase, count in cvd_df['phase'].value_counts().items():
            logger.info(f"  {phase}: {count}")

        logger.info("\nStatus distribution:")
        for status, count in cvd_df['status'].value_counts().head(5).items():
            logger.info(f"  {status}: {count}")

        # Save
        output = Path(__file__).parent / 'cvd_trials.csv'
        cvd_df.to_csv(output, index=False)
        logger.info(f"\nSaved to: {output}")

    # --- Mode 2: RNA therapeutics (legacy) ---
    logger.info("\n\n2. RNA THERAPEUTICS MODE")
    logger.info("-" * 40)

    rna_parser = ClinicalTrialsParser(
        query_mode="rna",
        max_results=100
    )

    if rna_parser.download_data():
        rna_data = rna_parser.parse_data()
        rna_df = rna_data.get('clinical_trials')

        if rna_df is not None and len(rna_df) > 0:
            logger.info(f"Total RNA therapeutics trials: {len(rna_df)}")

            # Post-filter for CVD
            cvd_rna = rna_parser.filter_cardiovascular_trials(rna_df)
            logger.info(f"CVD-related RNA trials: {len(cvd_rna)}")

    # --- Mode 3: Custom query ---
    logger.info("\n\n3. CUSTOM QUERY MODE")
    logger.info("-" * 40)

    custom_parser = ClinicalTrialsParser(
        query_mode="custom",
        query_term="SGLT2 inhibitor",
        query_field="query.intr",
        max_results=50
    )

    if custom_parser.download_data():
        custom_data = custom_parser.parse_data()
        custom_df = custom_data.get('clinical_trials')

        if custom_df is not None and len(custom_df) > 0:
            logger.info(f"Total SGLT2 inhibitor trials: {len(custom_df)}")

    logger.info("\n" + "=" * 70)
    logger.info("Example completed!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
