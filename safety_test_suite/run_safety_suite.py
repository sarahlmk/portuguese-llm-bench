#!/usr/bin/env python3
"""Orchestrator for the Safety / Fairness / Toxicity test suite.

Reads safety_suite_config.toml, invokes each enabled battery via subprocess
(reusing existing benchmark scripts), and then generates a consolidated
report with pass/fail verdicts per risk category.

Usage:
    python run_safety_suite.py                              # all batteries
    python run_safety_suite.py --batteries security         # one battery
    python run_safety_suite.py --smoke-test                 # quick CI check
    python run_safety_suite.py --model-version v1.2         # tag results
    python run_safety_suite.py --config custom_config.toml  # custom config
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redefine]
    except ModuleNotFoundError:
        raise SystemExit(
            "No TOML parser available. Use Python 3.11+ or: pip install tomli"
        ) from None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "safety_suite_config.toml")

BATTERY_REGISTRY: dict[str, dict] = {
    "security": {
        "script": os.path.join(REPO_ROOT, "refusals_harmful_requests", "run_refusals.py"),
        "results_subdir": "do_not_answer",
        "risk_label": "Security (Harmful Request Refusal)",
    },
    "fairness": {
        "script": os.path.join(REPO_ROOT, "sociocultural_bias", "run_stereoset.py"),
        "results_subdir": "stereoset",
        "risk_label": "Fairness (Sociocultural Bias)",
    },
    "toxicity": {
        "script": os.path.join(REPO_ROOT, "toxicity_benchmark", "run_toxicity.py"),
        "results_subdir": "toxicity",
        "risk_label": "Toxicity (Harmful Content Generation)",
    },
}


def load_config(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _build_output_dir(base: str, model_name: str, battery_name: str) -> str:
    return os.path.join(base, model_name, battery_name)


def _build_security_cmd(
    cfg: dict, output_dir: str, smoke_limit: int | None,
) -> list[str]:
    model = cfg["model"]
    opts = cfg.get("battery_options", {}).get("security", {})
    cmd = [
        sys.executable,
        BATTERY_REGISTRY["security"]["script"],
        "--base-url", model["base_url"],
        "--model", model["model_id"],
        "--output-dir", output_dir,
        "--classifier", opts.get("classifier", "gpt4"),
        "--classifier-model", opts.get("classifier_model", "gpt-4o"),
        "--num-concurrent", str(opts.get("num_concurrent", 4)),
    ]
    if opts.get("classifier_base_url"):
        cmd.extend(["--classifier-base-url", opts["classifier_base_url"]])
    classifier_key = opts.get("classifier_api_key") or ""
    if not classifier_key and "openrouter" in opts.get("classifier_base_url", ""):
        classifier_key = os.environ.get("OPENROUTER_API_KEY", "")
    if classifier_key:
        cmd.extend(["--classifier-api-key", classifier_key])
    if smoke_limit is not None:
        cmd.extend(["--limit", str(smoke_limit)])
    return cmd


def _build_fairness_cmd(
    cfg: dict, output_dir: str, smoke_limit: int | None,
) -> list[str]:
    model = cfg["model"]
    opts = cfg.get("battery_options", {}).get("fairness", {})
    cmd = [
        sys.executable,
        BATTERY_REGISTRY["fairness"]["script"],
        "--base-url", model["base_url"],
        "--model", model["model_id"],
        "--output-dir", output_dir,
        "--num-concurrent", str(opts.get("num_concurrent", 4)),
        "--temperature", str(opts.get("temperature", 0.0)),
    ]
    if smoke_limit is not None:
        cmd.extend(["--limit", str(smoke_limit)])
    return cmd


def _build_toxicity_cmd(
    cfg: dict, output_dir: str, smoke_limit: int | None,
) -> list[str]:
    model = cfg["model"]
    opts = cfg.get("battery_options", {}).get("toxicity", {})
    cmd = [
        sys.executable,
        BATTERY_REGISTRY["toxicity"]["script"],
        "--base-url", model["base_url"],
        "--model", model["model_id"],
        "--output-dir", output_dir,
        "--scorer", opts.get("scorer", "openai"),
        "--num-samples", str(opts.get("num_samples", 25)),
        "--temperature", str(opts.get("temperature", 1.0)),
        "--top-p", str(opts.get("top_p", 0.9)),
    ]
    if opts.get("scorer_api_key"):
        cmd.extend(["--scorer-api-key", opts["scorer_api_key"]])
    if smoke_limit is not None:
        cmd.extend(["--limit", str(smoke_limit)])
    return cmd


CMD_BUILDERS = {
    "security": _build_security_cmd,
    "fairness": _build_fairness_cmd,
    "toxicity": _build_toxicity_cmd,
}


def run_battery(
    battery_name: str,
    cfg: dict,
    output_base: str,
    smoke_test: bool,
) -> dict:
    """Run a single test battery and return a status dict."""
    info = BATTERY_REGISTRY[battery_name]
    model_name = cfg["model"]["name"]
    output_dir = _build_output_dir(output_base, model_name, info["results_subdir"])
    os.makedirs(output_dir, exist_ok=True)

    smoke_limits = cfg.get("smoke_test", {})
    smoke_limit = smoke_limits.get(f"{battery_name}_limit") if smoke_test else None

    cmd = CMD_BUILDERS[battery_name](cfg, output_dir, smoke_limit)

    logger.info("Running %s battery: %s", battery_name, " ".join(cmd))
    start = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200,
        )
        elapsed = round(time.monotonic() - start, 1)

        if result.returncode != 0:
            logger.error(
                "%s battery FAILED (exit %d):\nstdout: %s\nstderr: %s",
                battery_name, result.returncode,
                result.stdout[-2000:] if result.stdout else "",
                result.stderr[-2000:] if result.stderr else "",
            )
            return {
                "battery": battery_name,
                "status": "error",
                "exit_code": result.returncode,
                "elapsed_seconds": elapsed,
                "output_dir": output_dir,
                "error": result.stderr[-500:] if result.stderr else "Non-zero exit code",
            }

        logger.info("%s battery completed in %.1fs", battery_name, elapsed)
        return {
            "battery": battery_name,
            "status": "completed",
            "exit_code": 0,
            "elapsed_seconds": elapsed,
            "output_dir": output_dir,
        }

    except subprocess.TimeoutExpired:
        elapsed = round(time.monotonic() - start, 1)
        logger.error("%s battery TIMED OUT after %.1fs", battery_name, elapsed)
        return {
            "battery": battery_name,
            "status": "timeout",
            "exit_code": -1,
            "elapsed_seconds": elapsed,
            "output_dir": output_dir,
            "error": "Battery exceeded 2-hour timeout",
        }
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 1)
        logger.error("%s battery EXCEPTION: %s", battery_name, exc)
        return {
            "battery": battery_name,
            "status": "error",
            "exit_code": -1,
            "elapsed_seconds": elapsed,
            "output_dir": output_dir,
            "error": str(exc),
        }


def run_report_generator(
    cfg: dict,
    output_base: str,
    config_path: str,
    model_version: str | None,
    baseline: str | None,
) -> int:
    """Invoke generate_report.py and return its exit code."""
    report_script = os.path.join(SCRIPT_DIR, "generate_report.py")
    cmd = [
        sys.executable, report_script,
        "--config", config_path,
        "--output-dir", output_base,
    ]
    if model_version:
        cmd.extend(["--model-version", model_version])
    if baseline:
        cmd.extend(["--baseline", baseline])

    logger.info("Generating consolidated report ...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Safety / Fairness / Toxicity test suite orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help="Path to TOML config (default: safety_suite_config.toml)",
    )
    parser.add_argument(
        "--batteries", nargs="*",
        help="Run only specific batteries (default: all enabled in config)",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="Use reduced sample sizes for fast CI validation",
    )
    parser.add_argument(
        "--model-version", default=None,
        help="Model version tag (e.g. v1.1) to include in the report",
    )
    parser.add_argument(
        "--baseline", default=None,
        help="Path to a previous consolidated_report.json for comparison",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Override output directory (default: safety_test_suite/output)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config(args.config)
    output_base = args.output_dir or os.path.join(SCRIPT_DIR, "output")

    enabled = cfg.get("batteries", {}).get("enabled", list(BATTERY_REGISTRY.keys()))
    if args.batteries:
        enabled = [b for b in args.batteries if b in BATTERY_REGISTRY]
        invalid = [b for b in args.batteries if b not in BATTERY_REGISTRY]
        if invalid:
            logger.warning("Unknown batteries ignored: %s", invalid)

    if not enabled:
        sys.exit("No valid batteries to run.")

    print(f"\n{'=' * 60}")
    print("  Safety / Fairness / Toxicity Test Suite")
    print(f"{'=' * 60}")
    print(f"  Model:      {cfg['model']['name']}")
    print(f"  Endpoint:   {cfg['model']['base_url']}")
    print(f"  Batteries:  {', '.join(enabled)}")
    print(f"  Smoke test: {args.smoke_test}")
    if args.model_version:
        print(f"  Version:    {args.model_version}")
    print(f"{'=' * 60}\n")

    run_results = []
    overall_start = time.monotonic()

    for battery_name in enabled:
        print(f"{'─' * 60}")
        print(f"  Starting battery: {battery_name}")
        print(f"{'─' * 60}")
        status = run_battery(battery_name, cfg, output_base, args.smoke_test)
        run_results.append(status)

        if status["status"] == "completed":
            print(f"  >> {battery_name}: COMPLETED in {status['elapsed_seconds']}s\n")
        else:
            print(f"  >> {battery_name}: {status['status'].upper()} "
                  f"(exit {status['exit_code']})\n")

    overall_elapsed = round(time.monotonic() - overall_start, 1)

    run_manifest = {
        "suite": cfg.get("suite", {}),
        "model": cfg["model"],
        "model_version": args.model_version,
        "smoke_test": args.smoke_test,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_elapsed_seconds": overall_elapsed,
        "batteries": run_results,
    }

    manifest_path = os.path.join(output_base, cfg["model"]["name"], "run_manifest.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(run_manifest, f, indent=2, ensure_ascii=False)

    completed = [r for r in run_results if r["status"] == "completed"]
    failed = [r for r in run_results if r["status"] != "completed"]

    print(f"\n{'=' * 60}")
    print(f"  Suite execution finished in {overall_elapsed}s")
    print(f"  Completed: {len(completed)}/{len(run_results)}")
    if failed:
        print(f"  Failed:    {', '.join(r['battery'] for r in failed)}")
    print(f"{'=' * 60}\n")

    if not completed:
        print("No batteries completed. Skipping report generation.")
        sys.exit(1)

    report_exit = run_report_generator(
        cfg, output_base, args.config, args.model_version, args.baseline,
    )

    if failed:
        sys.exit(1)
    sys.exit(report_exit)


if __name__ == "__main__":
    main()
