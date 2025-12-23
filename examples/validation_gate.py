#!/usr/bin/env python3
"""
validation_gate.py - Example validation script demonstrating the Hard Gate pattern

This script shows how to implement a validation gate that blocks workflow
progression unless specific criteria are met. The key insight is that the
agent cannot decide if validation passed—the script decides, and the agent
reads the exit code.

EXIT CODES:
    0 - Validation PASSED. Agent may proceed to next state.
    1 - Validation FAILED. Agent must stop and report the error.

PATTERN PRINCIPLES:
    1. Check structural properties, not vibes
    2. Return binary pass/fail via exit code
    3. Provide clear error messages for failures
    4. Update project state with validation results
    5. Never allow the agent to override the result

This example validates that a translation covers the source text completely.
A translation is incomplete if the last translated content doesn't appear
near the end of the source.

USAGE:
    python validation_gate.py source.txt translation.json
    python validation_gate.py source.txt translation.json --project PROJECT_ID
"""

import json
import sys
import re
from pathlib import Path
from typing import Tuple, Dict, Any


# =============================================================================
# VALIDATION LOGIC
#
# The core validation functions check concrete, measurable properties.
# No subjective judgments. No "looks good to me."
# =============================================================================

def normalize_text(text: str) -> str:
    """
    Normalize text for comparison by removing formatting variations.

    This handles differences between source and translation that don't
    indicate missing content—just formatting quirks.
    """
    # Collapse whitespace
    text = ' '.join(text.split())

    # Normalize quotes (different sources use different quote styles)
    text = text.replace('«', '"').replace('»', '"')
    text = text.replace(''', "'").replace(''', "'")

    # Remove column markers like [Col. 0700D] that appear in some sources
    text = re.sub(r'\[Col\.\s*\d+[A-D]?\]', '', text)

    return text.strip()


def find_position_in_source(source: str, target: str) -> int:
    """
    Find where target text appears in source.

    Returns position (0-indexed), or -1 if not found.
    Tries progressively smaller fragments if full text isn't found.
    """
    source_norm = normalize_text(source)
    target_norm = normalize_text(target)

    # Try full target first
    pos = source_norm.find(target_norm)
    if pos >= 0:
        return pos

    # Try last 100 characters (handles minor trailing differences)
    if len(target_norm) > 100:
        pos = source_norm.find(target_norm[-100:])
        if pos >= 0:
            return pos

    # Try last 50 characters (more aggressive fallback)
    if len(target_norm) > 50:
        pos = source_norm.find(target_norm[-50:])
        if pos >= 0:
            return pos

    return -1


def check_translation_coverage(
    source_text: str,
    last_translated_chunk: str
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if translation covers the source text.

    This is the core validation: does the last translated content appear
    near the end of the source? If not, content was missed.

    Returns:
        Tuple of (passed, message, metrics)

    The metrics dict includes details for debugging and state updates.
    """
    metrics = {
        "source_length": len(source_text),
        "chunk_length": len(last_translated_chunk),
        "position_found": -1,
        "remaining_chars": 0,
        "remaining_pct": 0.0
    }

    # Find where the last translated content appears in source
    position = find_position_in_source(source_text, last_translated_chunk)

    if position == -1:
        # CRITICAL: The last translated text isn't in the source at all
        # This means something is very wrong
        return (
            False,
            "FATAL: Last translated chunk not found in source text. "
            "Translation may be from wrong source file.",
            metrics
        )

    metrics["position_found"] = position

    # Calculate how much source remains after this position
    source_norm = normalize_text(source_text)
    chunk_norm = normalize_text(last_translated_chunk)

    end_position = position + len(chunk_norm)
    remaining = len(source_norm) - end_position
    remaining_pct = (remaining / len(source_norm)) * 100

    metrics["remaining_chars"] = remaining
    metrics["remaining_pct"] = remaining_pct

    # Decision thresholds
    # More than 500 chars remaining = definitely incomplete
    # More than 100 chars = suspicious, may be incomplete
    # Less than 100 chars = probably just closing punctuation/formatting

    if remaining > 500:
        return (
            False,
            f"INCOMPLETE: Translation ends at {remaining_pct:.1f}% through source. "
            f"Approximately {remaining} characters remain untranslated. "
            f"The translation is missing the ending of the document.",
            metrics
        )

    if remaining > 100:
        return (
            False,
            f"WARNING: {remaining} characters ({remaining_pct:.1f}%) remain after "
            f"last translated chunk. Please verify this is just formatting, "
            f"not actual content.",
            metrics
        )

    return (
        True,
        f"PASSED: Translation covers source text. "
        f"Only {remaining} characters ({remaining_pct:.1f}%) remaining (formatting only).",
        metrics
    )


def check_natural_ending(last_chunk: str) -> Tuple[bool, str]:
    """
    Check if translation ends at a natural stopping point.

    Medieval texts have characteristic endings. A translation cut off
    mid-sentence will have telltale signs.
    """
    text = last_chunk.lower().strip()

    # Patterns that indicate incomplete sentences
    incomplete_patterns = [
        (r'\but\s*$', 'ends with "ut" (so that)—likely incomplete'),
        (r'\bquod\s*$', 'ends with "quod" (which/that)—likely incomplete'),
        (r'\bquia\s*$', 'ends with "quia" (because)—likely incomplete'),
        (r'\bet\s*$', 'ends with "et" (and)—likely incomplete'),
        (r',\s*$', 'ends with comma—sentence incomplete'),
        (r':\s*$', 'ends with colon—expecting continuation'),
    ]

    warnings = []
    for pattern, message in incomplete_patterns:
        if re.search(pattern, text):
            warnings.append(message)

    if warnings:
        return (
            False,
            "INCOMPLETE ENDING: " + "; ".join(warnings)
        )

    # Check for proper ending markers
    good_endings = ['amen', 'amen.', '.', '?', '!']
    if not any(text.rstrip().endswith(e) for e in good_endings):
        return (
            False,
            "WARNING: Translation doesn't end with typical closing marker "
            "(Amen, period, etc.)"
        )

    return (True, "Ending appears natural")


# =============================================================================
# MAIN VALIDATION ENTRY POINT
# =============================================================================

def validate_translation(
    source_path: Path,
    translation_path: Path,
    verbose: bool = True
) -> Tuple[bool, Dict[str, Any]]:
    """
    Run all validation checks on a translation.

    Args:
        source_path: Path to source text file
        translation_path: Path to translation JSON
        verbose: If True, print detailed output

    Returns:
        Tuple of (passed, results_dict)
    """
    results = {
        "source_path": str(source_path),
        "translation_path": str(translation_path),
        "passed": True,
        "errors": [],
        "warnings": [],
        "metrics": {}
    }

    # Load source text
    try:
        source_text = source_path.read_text(encoding='utf-8')
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"Cannot read source file: {e}")
        return False, results

    # Load and parse translation JSON
    try:
        with open(translation_path, 'r', encoding='utf-8') as f:
            translation = json.load(f)
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"Cannot parse translation JSON: {e}")
        return False, results

    # Get chunks from translation
    chunks = translation.get('chunks', [])
    if not chunks:
        results["passed"] = False
        results["errors"].append("Translation has no chunks")
        return False, results

    results["metrics"]["chunk_count"] = len(chunks)

    # Get the last chunk's content
    last_chunk = chunks[-1]
    last_latin = last_chunk.get('latin', last_chunk.get('original_latin', ''))

    if not last_latin:
        results["passed"] = False
        results["errors"].append("Last chunk has no Latin text")
        return False, results

    if verbose:
        print("=" * 60)
        print("TRANSLATION VALIDATION")
        print("=" * 60)
        print(f"Source: {source_path}")
        print(f"Translation: {translation_path}")
        print(f"Chunks: {len(chunks)}")
        print()

    # =========================================================================
    # CHECK 1: Does translation cover the source?
    # =========================================================================
    if verbose:
        print("-" * 60)
        print("CHECK 1: Source Coverage")
        print("-" * 60)

    passed, message, metrics = check_translation_coverage(source_text, last_latin)
    results["metrics"].update(metrics)

    if verbose:
        print(message)
        print()

    if not passed:
        results["passed"] = False
        results["errors"].append(message.split('.')[0])  # First sentence

    # =========================================================================
    # CHECK 2: Does translation end naturally?
    # =========================================================================
    if verbose:
        print("-" * 60)
        print("CHECK 2: Natural Ending")
        print("-" * 60)

    passed, message = check_natural_ending(last_latin)

    if verbose:
        print(message)
        print()

    if not passed:
        if "INCOMPLETE" in message:
            results["passed"] = False
            results["errors"].append(message)
        else:
            results["warnings"].append(message)

    # =========================================================================
    # FINAL VERDICT
    # =========================================================================
    if verbose:
        print("=" * 60)
        if results["passed"]:
            print("VALIDATION PASSED")
            print("Safe to proceed to next pipeline stage.")
        else:
            print("VALIDATION FAILED")
            print("DO NOT proceed. Fix the issues and re-run validation.")
            for error in results["errors"]:
                print(f"  ERROR: {error}")
        print("=" * 60)

    return results["passed"], results


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate translation completeness (Hard Gate pattern example)"
    )
    parser.add_argument("source_file", help="Path to source text file")
    parser.add_argument("translation_file", help="Path to translation JSON")
    parser.add_argument("--project", "-p", help="Project ID (optional, for state updates)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress verbose output")

    args = parser.parse_args()

    source_path = Path(args.source_file)
    translation_path = Path(args.translation_file)

    # Validate file existence
    if not source_path.exists():
        print(f"ERROR: Source file not found: {source_path}")
        sys.exit(1)

    if not translation_path.exists():
        print(f"ERROR: Translation file not found: {translation_path}")
        sys.exit(1)

    # Run validation
    passed, results = validate_translation(
        source_path,
        translation_path,
        verbose=not args.quiet
    )

    # =========================================================================
    # EXIT CODE IS THE GATE
    #
    # This is the critical part: the exit code determines whether the
    # agent can proceed. The agent reads this result; it cannot override it.
    # =========================================================================
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
