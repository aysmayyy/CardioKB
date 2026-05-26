#!/usr/bin/env python3
"""
eval_pipeline.py — Unified evaluation runner for the CardioKB pipeline.

Runs all evaluation stages in sequence and produces a combined report.

Stages:
  1. download  — Validate raw data files (eval_download.py)
  2. parser    — Validate parsed TSV files (eval_parser.py)
  3. load      — Validate TSV→Graph loading (eval_load.py)
  4. graph     — Validate live Memgraph (eval_graph.py)

Usage:
    python eval/eval_pipeline.py                    # Run all stages
    python eval/eval_pipeline.py --stage graph      # Run single stage
    python eval/eval_pipeline.py --skip download    # Skip a stage
    python eval/eval_pipeline.py --strict           # Fail on Tier 1 errors
    python eval/eval_pipeline.py --output report.json
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).parent

STAGES = {
    "download": {
        "script": "eval_download.py",
        "description": "Validate raw data downloads",
        "requires_memgraph": False,
    },
    "parser": {
        "script": "eval_parser.py",
        "description": "Validate parsed TSV files",
        "requires_memgraph": False,
    },
    "load": {
        "script": "eval_load.py",
        "description": "Validate TSV→Graph loading",
        "requires_memgraph": True,
    },
    "graph": {
        "script": "eval_graph.py",
        "description": "Validate live Memgraph",
        "requires_memgraph": True,
    },
}


def run_stage(stage_name: str, stage_config: dict, strict: bool = False) -> dict:
    """Run a single evaluation stage and return results."""
    script_path = EVAL_DIR / stage_config["script"]

    if not script_path.exists():
        return {
            "status": "ERROR",
            "error": f"Script not found: {script_path}",
            "duration_sec": 0,
            "metrics": [],
        }

    start_time = time.time()

    try:
        # Run the script and capture JSON output
        cmd = [sys.executable, str(script_path)]
        if strict:
            cmd.append("--strict")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout per stage
            cwd=str(EVAL_DIR.parent),
        )

        duration = round(time.time() - start_time, 2)

        # Parse JSON output (find the JSON block between { and })
        stdout = result.stdout.strip()
        json_start = stdout.find("{")
        json_end = stdout.rfind("}") + 1

        if json_start != -1 and json_end > json_start:
            json_text = stdout[json_start:json_end]
            try:
                report = json.loads(json_text)
                metrics = report.get("metrics", [])
                summary = report.get("summary", {})

                # Count failures
                tier1_failures = [m for m in metrics
                                 if m.get("tier") == 1 and m.get("note")
                                 and ("BLOCKING" in m["note"] or "failure" in m["note"].lower())]

                status = "FAIL" if tier1_failures else "PASS"

                return {
                    "status": status,
                    "duration_sec": duration,
                    "metrics": metrics,
                    "summary": summary,
                    "tier1_failures": len(tier1_failures),
                    "total_metrics": len(metrics),
                }
            except json.JSONDecodeError as e:
                return {
                    "status": "ERROR",
                    "error": f"Failed to parse JSON output: {e}",
                    "duration_sec": duration,
                    "stdout": result.stdout[-1000:],  # Last 1000 chars
                    "metrics": [],
                }
        else:
            return {
                "status": "ERROR",
                "error": "No JSON output found",
                "duration_sec": duration,
                "stdout": result.stdout[-1000:],
                "stderr": result.stderr[-500:] if result.stderr else None,
                "metrics": [],
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "error": "Stage timed out after 600 seconds",
            "duration_sec": 600,
            "metrics": [],
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "duration_sec": round(time.time() - start_time, 2),
            "metrics": [],
        }


def main():
    parser = argparse.ArgumentParser(
        description="Run CardioKB pipeline evaluation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Stages:
  download  — Validate raw data downloads
  parser    — Validate parsed TSV files
  load      — Validate TSV→Graph loading
  graph     — Validate live Memgraph

Examples:
  %(prog)s                        # Run all stages
  %(prog)s --stage graph          # Run only graph validation
  %(prog)s --skip download        # Skip download validation
  %(prog)s --strict --output r.json
        """
    )
    parser.add_argument("--stage", "-s", choices=list(STAGES.keys()),
                        help="Run only this stage")
    parser.add_argument("--skip", action="append", choices=list(STAGES.keys()),
                        default=[], help="Skip this stage (can be repeated)")
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Write JSON report to FILE")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with error code 1 on any Tier 1 failure")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Minimal output (just summary)")
    args = parser.parse_args()

    # Determine which stages to run
    if args.stage:
        stages_to_run = [args.stage]
    else:
        stages_to_run = [s for s in STAGES if s not in args.skip]

    print("=" * 60)
    print("CardioKB Pipeline Evaluation")
    print("=" * 60)
    print(f"Stages: {', '.join(stages_to_run)}")
    print()

    results = {}
    total_start = time.time()
    any_failures = False

    for stage_name in stages_to_run:
        stage_config = STAGES[stage_name]
        print(f"[{stage_name.upper()}] {stage_config['description']}...")

        result = run_stage(stage_name, stage_config, args.strict)
        results[stage_name] = result

        status = result["status"]
        duration = result["duration_sec"]
        metrics_count = result.get("total_metrics", len(result.get("metrics", [])))

        if status == "PASS":
            print(f"  ✓ PASS ({metrics_count} metrics, {duration}s)")
        elif status == "FAIL":
            print(f"  ✗ FAIL ({result.get('tier1_failures', 0)} failures, {duration}s)")
            any_failures = True
        else:
            print(f"  ⚠ {status}: {result.get('error', 'Unknown error')}")
            any_failures = True

        print()

    total_duration = round(time.time() - total_start, 2)

    # Build combined report
    all_metrics = []
    for stage_name, result in results.items():
        for m in result.get("metrics", []):
            m["stage"] = stage_name
            all_metrics.append(m)

    # Summary
    passed = sum(1 for r in results.values() if r["status"] == "PASS")
    failed = sum(1 for r in results.values() if r["status"] == "FAIL")
    errors = sum(1 for r in results.values() if r["status"] not in ("PASS", "FAIL"))

    tier1_total = sum(r.get("tier1_failures", 0) for r in results.values())

    report = {
        "run_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "pipeline_version": "1.0.0",
        "stages_run": stages_to_run,
        "stages": {name: {
            "status": r["status"],
            "duration_sec": r["duration_sec"],
            "total_metrics": r.get("total_metrics", 0),
            "tier1_failures": r.get("tier1_failures", 0),
            "summary": r.get("summary"),
        } for name, r in results.items()},
        "summary": {
            "total_duration_sec": total_duration,
            "stages_passed": passed,
            "stages_failed": failed,
            "stages_error": errors,
            "total_metrics": len(all_metrics),
            "tier1_failures": tier1_total,
        },
        "metrics": all_metrics,
    }

    # Output
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        print(f"Report written to {args.output}")
        print()

    # Final summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Stages: {passed} passed, {failed} failed, {errors} errors")
    print(f"Metrics: {len(all_metrics)} total, {tier1_total} Tier 1 failures")
    print(f"Duration: {total_duration}s")
    print()

    if any_failures:
        print("❌ PIPELINE VALIDATION FAILED")
        if args.strict:
            sys.exit(1)
    else:
        print("✅ PIPELINE VALIDATION PASSED")


if __name__ == "__main__":
    main()
