"""
Test query specifically for cardiovascular disease trials to see total CVD trial count.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers import ClinicalTrialsParser
import logging

logging.basicConfig(level=logging.INFO)


def main():
    """Query for cardiovascular disease trials directly."""

    print("=" * 70)
    print("Testing Direct CVD Query")
    print("=" * 70)

    # Query 1: RNA therapeutics (what we've been doing)
    print("\n1. RNA therapeutics trials:")
    parser1 = ClinicalTrialsParser(query_term="RNA therapeutics", max_results=500)
    parser1.download_data()
    data1 = parser1.parse_data()
    trials1 = data1['rna_therapeutics_trials']
    cvd1 = parser1.filter_cardiovascular_trials(trials1)
    print(f"   Total: {len(trials1)} trials")
    print(f"   CVD: {len(cvd1)} trials ({len(cvd1)/len(trials1)*100:.1f}%)")

    # Query 2: Cardiovascular disease directly
    print("\n2. Cardiovascular disease trials:")
    parser2 = ClinicalTrialsParser(query_term="cardiovascular disease", max_results=500)
    parser2.download_data()
    data2 = parser2.parse_data()
    trials2 = data2['rna_therapeutics_trials']
    print(f"   Total CVD trials: {len(trials2)}")

    # Query 3: Heart failure
    print("\n3. Heart failure trials:")
    parser3 = ClinicalTrialsParser(query_term="heart failure", max_results=500)
    parser3.download_data()
    data3 = parser3.parse_data()
    trials3 = data3['rna_therapeutics_trials']
    print(f"   Total heart failure trials: {len(trials3)}")

    # Query 4: Stroke
    print("\n4. Stroke trials:")
    parser4 = ClinicalTrialsParser(query_term="stroke", max_results=500)
    parser4.download_data()
    data4 = parser4.parse_data()
    trials4 = data4['rna_therapeutics_trials']
    print(f"   Total stroke trials: {len(trials4)}")

    print("\n" + "=" * 70)
    print("Conclusion:")
    print(f"  - RNA therapeutics is still emerging for CVD")
    print(f"  - Only {len(cvd1)/len(trials1)*100:.1f}% of RNA therapeutic trials are CVD-related")
    print(f"  - But there are {len(trials2)} CVD trials overall when queried directly")
    print("=" * 70)


if __name__ == "__main__":
    main()
