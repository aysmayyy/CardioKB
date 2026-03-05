"""
Example script demonstrating the ClinicalTrialsParser for RNA therapeutics.

This script shows how to:
1. Query ClinicalTrials.gov API for RNA therapeutics
2. Parse the data into a structured DataFrame
3. Filter for cardiovascular-related trials
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
    logger.info("ClinicalTrials.gov RNA Therapeutics Parser Example")
    logger.info("=" * 70)

    # Initialize parser for RNA therapeutics
    parser = ClinicalTrialsParser(
        query_term="RNA therapeutics",
        max_results=500  # Limit for demo purposes
    )

    # Download data from API
    logger.info("\n1. Downloading RNA therapeutics trials from ClinicalTrials.gov...")
    success = parser.download_data()

    if not success:
        logger.error("Failed to download data. Exiting.")
        return

    # Parse data
    logger.info("\n2. Parsing trial data...")
    data = parser.parse_data()
    trials_df = data.get('rna_therapeutics_trials')

    if trials_df is None or len(trials_df) == 0:
        logger.warning("No trials found.")
        return

    # Display basic statistics
    logger.info("\n3. Summary Statistics:")
    logger.info(f"Total trials retrieved: {len(trials_df)}")

    logger.info("\nTop 5 most common conditions:")
    condition_counts = trials_df['condition'].value_counts().head(5)
    for condition, count in condition_counts.items():
        logger.info(f"  - {condition[:60]}: {count}")

    logger.info("\nPhase distribution:")
    phase_counts = trials_df['phase'].value_counts()
    for phase, count in phase_counts.items():
        logger.info(f"  - {phase}: {count}")

    logger.info("\nStatus distribution:")
    status_counts = trials_df['status'].value_counts()
    for status, count in status_counts.items():
        logger.info(f"  - {status}: {count}")

    # Filter for cardiovascular trials
    logger.info("\n4. Filtering for cardiovascular disease trials...")
    cvd_trials = parser.filter_cardiovascular_trials(trials_df)

    if len(cvd_trials) > 0:
        logger.info(f"\nFound {len(cvd_trials)} cardiovascular trials:")
        logger.info(f"\nSample cardiovascular trials:")
        for idx, row in cvd_trials.head(5).iterrows():
            logger.info(f"\n  Trial ID: {row['trial_id']}")
            logger.info(f"  Title: {row['title'][:70]}...")
            logger.info(f"  Condition: {row['condition'][:60]}...")
            logger.info(f"  Phase: {row['phase']}")
            logger.info(f"  Status: {row['status']}")

    # Save to CSV
    output_file = Path(__file__).parent / 'rna_therapeutics_trials.csv'
    trials_df.to_csv(output_file, index=False)
    logger.info(f"\n5. Saved full results to: {output_file}")

    cvd_output_file = Path(__file__).parent / 'rna_cardiovascular_trials.csv'
    if len(cvd_trials) > 0:
        cvd_trials.to_csv(cvd_output_file, index=False)
        logger.info(f"   Saved cardiovascular trials to: {cvd_output_file}")

    logger.info("\n" + "=" * 70)
    logger.info("Example completed successfully!")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
