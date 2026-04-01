#!/usr/bin/env python3
"""Compare two StereoSet evaluation runs (before vs. after).

Reads two results.json files produced by run_stereoset.py and prints a
side-by-side table with delta values. A positive SS delta toward 50 is
marked as an improvement; away from 50 is a regression.

Usage:
    python compare_stereoset.py \\
        output/stereoset/qwen3-32b/results.json \\
        output/stereoset/functionary-pt-BR-v1.1/results.json \\
        --output comparison.json
"""

from __future__ import annotations

import argparse
import json
import sys


def ss_bias(ss: float) -> float:
    """Distance from the ideal SS of 50. Lower is better."""
    return abs(ss - 50)


def load_results(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compare(before: dict, after: dict) -> dict:
    """Build a comparison dict with deltas for all metrics."""

    def _ss_direction(ss: float) -> str:
        if ss > 50:
            return "pro-stereotype"
        elif ss < 50:
            return "anti-stereotype"
        return "neutral"

    def _diff(b: dict, a: dict) -> dict:
        lms_delta = a["lms"] - b["lms"]
        ss_delta = a["ss"] - b["ss"]
        icat_delta = a["icat"] - b["icat"]
        bias_before = ss_bias(b["ss"])
        bias_after = ss_bias(a["ss"])
        bias_improved = bias_after < bias_before
        return {
            "before": {"lms": b["lms"], "ss": b["ss"], "icat": b["icat"]},
            "after":  {"lms": a["lms"], "ss": a["ss"], "icat": a["icat"]},
            "delta":  {
                "lms": round(lms_delta, 2),
                "ss": round(ss_delta, 2),
                "icat": round(icat_delta, 2),
            },
            "ss_bias_before": round(bias_before, 2),
            "ss_bias_after": round(bias_after, 2),
            "ss_direction_before": _ss_direction(b["ss"]),
            "ss_direction_after": _ss_direction(a["ss"]),
            "bias_improved": bias_improved,
        }

    bm = before["metrics"]
    am = after["metrics"]

    result = {
        "overall": _diff(bm["overall"], am["overall"]),
        "per_category": {},
    }

    all_cats = sorted(
        set(bm.get("per_category", {}).keys())
        | set(am.get("per_category", {}).keys())
    )
    for cat in all_cats:
        b_cat = bm.get("per_category", {}).get(cat)
        a_cat = am.get("per_category", {}).get(cat)
        if b_cat and a_cat:
            result["per_category"][cat] = _diff(b_cat, a_cat)

    result["before_model"] = before.get("config", {}).get("model", "unknown")
    result["after_model"] = after.get("config", {}).get("model", "unknown")

    return result


def print_report(comp: dict) -> None:
    bmodel = comp["before_model"]
    amodel = comp["after_model"]

    print(f"\n{'=' * 76}")
    print("  StereoSet Bias Comparison Report")
    print(f"{'=' * 76}")
    print(f"  Before: {bmodel}")
    print(f"  After:  {amodel}")
    print(f"{'─' * 76}")

    def _row(label: str, data: dict) -> None:
        b, a, d = data["before"], data["after"], data["delta"]
        direction = data.get("ss_direction_after", "")
        sign = lambda v: f"+{v}" if v > 0 else str(v)
        print(
            f"  {label:12s}  "
            f"LMS {b['lms']:6.2f} -> {a['lms']:6.2f} ({sign(d['lms']):>6s})  "
            f"SS {b['ss']:6.2f} -> {a['ss']:6.2f} ({sign(d['ss']):>6s})  "
            f"ICAT {b['icat']:6.2f} -> {a['icat']:6.2f} ({sign(d['icat']):>6s})"
        )
        print(
            f"  {'':12s}  "
            f"SS bias: {data['ss_bias_before']:.2f} -> "
            f"{data['ss_bias_after']:.2f}  "
            f"[direction: {direction}]"
        )

    _row("OVERALL", comp["overall"])
    print(f"{'─' * 76}")

    for cat in sorted(comp["per_category"]):
        _row(cat, comp["per_category"][cat])

    print(f"{'=' * 76}")

    o = comp["overall"]
    after_ss = o["after"]["ss"]
    direction = o.get("ss_direction_after", "")
    pro_stereo = after_ss > 50

    if pro_stereo:
        if o["bias_improved"]:
            verdict = (
                "Pro-stereotype bias DECREASED after fine-tuning "
                f"(SS {o['before']['ss']:.2f} -> {after_ss:.2f}, closer to ideal 50)."
            )
        else:
            verdict = (
                "Pro-stereotype bias INCREASED after fine-tuning "
                f"(SS {o['before']['ss']:.2f} -> {after_ss:.2f}, further from ideal 50)."
            )
    else:
        verdict = (
            f"The model is anti-stereotypical (SS={after_ss:.2f}, below the ideal 50), "
            f"meaning it actively avoids stereotypical associations. "
            f"The model does NOT reinforce social stereotypes."
        )
        if not o["bias_improved"]:
            verdict += (
                f"\n  Note: Distance from ideal 50 grew slightly "
                f"({o['ss_bias_before']:.2f} -> {o['ss_bias_after']:.2f}), "
                f"indicating stronger anti-stereotype preference after fine-tuning."
            )

    print(f"\n  CONCLUSION: {verdict}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare two StereoSet results (before vs. after)",
    )
    parser.add_argument(
        "before", help="Path to results.json from the baseline model",
    )
    parser.add_argument(
        "after", help="Path to results.json from the fine-tuned model",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Write comparison JSON to this file (optional)",
    )
    args = parser.parse_args()

    before = load_results(args.before)
    after = load_results(args.after)
    comp = compare(before, after)
    print_report(comp)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(comp, f, indent=2, ensure_ascii=False)
        print(f"\n  Comparison saved to: {args.output}")


if __name__ == "__main__":
    main()
