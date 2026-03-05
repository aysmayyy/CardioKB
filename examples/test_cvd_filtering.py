"""
Test script to verify CVD term filtering works correctly.

This script tests:
1. Loading CVD terms from the ontology file
2. Filtering trials using the comprehensive CVD terminology
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import load_cvd_terms, get_cvd_search_pattern, is_cardiovascular_related


def main():
    """Test CVD term loading and filtering."""

    print("=" * 70)
    print("CVD Term Filtering Test")
    print("=" * 70)

    # Test 1: Load CVD terms
    print("\n1. Loading CVD terms from ontology...")
    cvd_terms = load_cvd_terms()
    print(f"✓ Loaded {len(cvd_terms)} unique CVD terms")

    # Display some terms
    print("\nSample terms (first 15):")
    for i, term in enumerate(sorted(cvd_terms)[:15]):
        print(f"  - {term}")

    # Test 2: Search pattern generation
    print("\n2. Generating search pattern...")
    pattern = get_cvd_search_pattern()
    print(f"✓ Pattern length: {len(pattern)} characters")
    print(f"   Contains {pattern.count('|') + 1} alternations")

    # Test 3: Test text matching
    print("\n3. Testing text matching...")
    test_cases = [
        ("Study of Heart Failure in Elderly Patients", True),
        ("Atrial Fibrillation Treatment Trial", True),
        ("COVID-19 Vaccine Efficacy Study", False),
        ("Myocardial Infarction Prevention", True),
        ("Diabetes Management Protocol", False),
        ("Stroke Recovery in Young Adults", True),
        ("Hypertrophic Cardiomyopathy Screening", True),
    ]

    all_passed = True
    for text, expected in test_cases:
        result = is_cardiovascular_related(text, cvd_terms)
        status = "✓" if result == expected else "✗"
        all_passed = all_passed and (result == expected)
        print(f"  {status} '{text[:50]}...' -> {result} (expected {expected})")

    # Summary
    print("\n" + "=" * 70)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print("=" * 70)


if __name__ == "__main__":
    main()
