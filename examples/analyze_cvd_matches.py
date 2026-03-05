"""
Diagnostic script to analyze CVD term matching in the trial dataset.

Shows:
1. Which CVD terms are actually matching
2. Sample trials for each matched term
3. Potential trials that might be CVD-related but not caught
"""

import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import load_cvd_terms


def main():
    """Analyze CVD matching in the dataset."""

    print("=" * 70)
    print("CVD Term Matching Analysis")
    print("=" * 70)

    # Load the full dataset
    trials_file = Path(__file__).parent / 'rna_therapeutics_trials.csv'
    cvd_file = Path(__file__).parent / 'rna_cardiovascular_trials.csv'

    if not trials_file.exists():
        print(f"Error: {trials_file} not found. Run clinicaltrials_rna_example.py first.")
        return

    trials_df = pd.read_csv(trials_file)
    cvd_df = pd.read_csv(cvd_file)

    print(f"\nDataset: {len(trials_df)} total trials")
    print(f"CVD trials found: {len(cvd_df)}")
    print(f"Percentage: {len(cvd_df)/len(trials_df)*100:.1f}%")

    # Load CVD terms
    cvd_terms = load_cvd_terms()
    print(f"\nUsing {len(cvd_terms)} CVD terms from ontology")

    # Analyze which terms are matching
    print("\n" + "=" * 70)
    print("CVD Terms That Matched:")
    print("=" * 70)

    term_matches = {}
    for term in sorted(cvd_terms):
        matching_trials = cvd_df[
            cvd_df['condition'].str.contains(term, case=False, na=False) |
            cvd_df['title'].str.contains(term, case=False, na=False)
        ]
        if len(matching_trials) > 0:
            term_matches[term] = len(matching_trials)

    for term, count in sorted(term_matches.items(), key=lambda x: -x[1]):
        print(f"  ✓ '{term}': {count} trial(s)")

    # Show terms that didn't match
    unmatched_terms = cvd_terms - set(term_matches.keys())
    print(f"\n{len(unmatched_terms)} CVD terms did not match any trials:")
    for term in sorted(unmatched_terms)[:10]:
        print(f"  - {term}")
    if len(unmatched_terms) > 10:
        print(f"  ... and {len(unmatched_terms) - 10} more")

    # Look for potential missed trials (terms like "cardio", "vascular", etc.)
    print("\n" + "=" * 70)
    print("Potential Additional Cardiovascular-Related Terms in Dataset:")
    print("=" * 70)

    # Get non-CVD trials
    non_cvd_df = trials_df[~trials_df['trial_id'].isin(cvd_df['trial_id'])]

    # Look for partial matches
    potential_terms = [
        'cardio', 'vascular', 'cardiac', 'vessel', 'arterial',
        'venous', 'circulatory', 'blood pressure', 'cholesterol'
    ]

    found_potential = False
    for term in potential_terms:
        matching = non_cvd_df[
            non_cvd_df['condition'].str.contains(term, case=False, na=False) |
            non_cvd_df['title'].str.contains(term, case=False, na=False)
        ]
        if len(matching) > 0:
            found_potential = True
            print(f"\n'{term}' appears in {len(matching)} non-CVD trial(s):")
            for _, trial in matching.head(3).iterrows():
                print(f"  - {trial['trial_id']}: {trial['title'][:60]}...")
                print(f"    Condition: {trial['condition'][:60]}...")

    if not found_potential:
        print("  ✓ No additional cardiovascular-related terms found")

    print("\n" + "=" * 70)
    print(f"Summary: {len(cvd_df)} CVD trials identified using {len(term_matches)} matching terms")
    print("=" * 70)


if __name__ == "__main__":
    main()
