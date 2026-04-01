#!/usr/bin/env python3
"""Run lm-eval across models and tasks defined in eval_config.toml.

Uses the lm_eval Python API directly (no subprocess).

Usage:
    python run_eval.py                              # all models x all tasks
    python run_eval.py --models Qwen3.5-27b         # one model, all tasks
    python run_eval.py --tasks portuguese            # all models, one task
    python run_eval.py --dry-run                     # print params only
    python run_eval.py --save-all-samples            # keep all 64 responses in JSONL

Generation parameters (max_gen_toks, temperature, top_p, top_k, min_p) are NOT
baked into the task YAMLs so they can vary per model via gen_kwargs in the TOML
or --gen-kwargs on the CLI.

Sampling & self-consistency:
    Task YAMLs use ``repeats: 64`` and ``do_sample: true`` with
    ``temperature: 0.7``. The filter pipeline applies majority_vote (discrete
    tasks) or median_float_vote (STS) before take_first.

Reasoning: monkey-patches LocalChatCompletion.parse_generations so API fields
``reasoning`` / ``reasoning_content`` are preserved in the output.

Output:
    output/{model}/{task}/results.json       -- aggregate scores
    output/{model}/{task}/samples_{task}.jsonl -- per-sample results
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
import sys
import traceback
from datetime import datetime

import lm_eval
import f1_utils  # noqa: F401 -- registers regex_last and median_float_vote filters
from lm_eval.utils import handle_non_serializable, make_table, sanitize_list

logger = logging.getLogger(__name__)

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def _patch_chat_completion_reasoning():
    """Monkey-patch LocalChatCompletion to pass reasoning through (wire format)."""
    from lm_eval.models import openai_completions as oc

    @staticmethod
    def parse_generations(outputs, **kwargs):
        res = []
        if not isinstance(outputs, list):
            outputs = [outputs]
        for out in outputs:
            try:
                tmp = [None] * len(out["choices"])
                for choices in out["choices"]:
                    msg = choices.get("message") or {}
                    content = msg.get("content")
                    if content is None:
                        content = ""
                    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
                    if reasoning is None:
                        reasoning = ""
                    if reasoning:
                        content = f"{_THINK_OPEN}{reasoning}{_THINK_CLOSE}{content}"
                    tmp[choices["index"]] = content
            except Exception:
                tmp = [""]
            res = res + tmp
        return res

    oc.LocalChatCompletion.parse_generations = parse_generations


_patch_chat_completion_reasoning()

try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        raise SystemExit(
            "No TOML parser available. Either:\n"
            "  - Use Python 3.11+ (has tomllib), e.g. python3.11 run_eval.py\n"
            "  - Or install tomli: pip install tomli\n"
            f"  (current interpreter: {sys.executable})"
        ) from None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "eval_config.toml")


def load_config(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _ensure_lm_eval_api_key():
    """local-chat-completions uses OPENAI_API_KEY for the Bearer header.
    Mirror OPENROUTER_API_KEY if set."""
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if or_key:
            os.environ["OPENAI_API_KEY"] = or_key


# ── Reasoning / think-tag helpers ────────────────────────────────────


def _split_reasoning_from_text(text: str) -> tuple[str, str]:
    if not isinstance(text, str) or not text.startswith(_THINK_OPEN):
        return "", text
    idx = text.find(_THINK_CLOSE, len(_THINK_OPEN))
    if idx == -1:
        return "", text
    reasoning = text[len(_THINK_OPEN) : idx]
    content = text[idx + len(_THINK_CLOSE) :]
    return reasoning, content


def _split_resps_structure(resps):
    if isinstance(resps, str):
        reasoning, content = _split_reasoning_from_text(resps)
        return content, reasoning
    if isinstance(resps, list):
        contents, reasons = [], []
        for x in resps:
            c, r = _split_resps_structure(x)
            contents.append(c)
            reasons.append(r)
        return contents, reasons
    return resps, ""


def _add_reasoning_content_to_samples(samples: dict) -> None:
    for _task_name, rows in samples.items():
        for sample in rows:
            if "resps" not in sample:
                continue
            content, reasoning = _split_resps_structure(sample["resps"])
            sample["resps"] = content
            sample["reasoning_content"] = reasoning
            if "filtered_resps" in sample:
                fc, _ = _split_resps_structure(sample["filtered_resps"])
                sample["filtered_resps"] = fc


# ── Prompt extraction helpers ────────────────────────────────────────


def _is_lm_eval_generation_kwargs(d: dict) -> bool:
    return any(
        k in d
        for k in (
            "until", "max_gen_toks", "do_sample",
            "temperature", "top_p", "top_k", "min_p", "repeats",
        )
    )


def _text_from_prompt_ctx(part) -> list[str]:
    out: list[str] = []
    if part is None:
        return out
    if isinstance(part, str):
        s = part.strip()
        if s.startswith("[") and '"role"' in s and '"content"' in s:
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                return [part]
            if isinstance(parsed, list):
                return _text_from_prompt_ctx(parsed)
        return [part]
    if isinstance(part, (list, tuple)):
        for x in part:
            out.extend(_text_from_prompt_ctx(x))
        return out
    if isinstance(part, dict):
        if "content" in part:
            out.extend(_text_from_prompt_ctx(part["content"]))
        elif isinstance(part.get("text"), str):
            out.append(part["text"])
        return out
    return out


def _extract_prompt_and_gen_kwargs(arguments) -> tuple[str, dict | None]:
    if not arguments:
        return "", None
    chunks: list[str] = []
    gen_kwargs: dict | None = None
    for req_args in arguments:
        if not isinstance(req_args, (list, tuple)):
            continue
        for item in req_args:
            if isinstance(item, dict) and _is_lm_eval_generation_kwargs(item):
                if gen_kwargs is None:
                    gen_kwargs = item
                continue
            chunks.extend(_text_from_prompt_ctx(item))
    prompt = "\n".join(s for s in chunks if s)
    return prompt, gen_kwargs


# ── JSONL output ─────────────────────────────────────────────────────


def _sample_row_compact(sample: dict) -> dict:
    """Compact JSONL row: doc_id, prompt, target, prediction only."""
    prompt, _ = _extract_prompt_and_gen_kwargs(sample.get("arguments"))
    prediction = ""
    if "filtered_resps" in sample:
        fr = sample["filtered_resps"]
        if isinstance(fr, list) and fr:
            prediction = str(fr[0]) if not isinstance(fr[0], str) else fr[0]
        elif isinstance(fr, str):
            prediction = fr

    target_val = str(sample.get("target", ""))

    row = {
        "doc_id": sample.get("doc_id"),
        "prompt": prompt,
        "target": target_val,
        "prediction": prediction,
    }

    for metric_name in ("exact_match", "f1_macro", "pearson", "mse"):
        if metric_name in sample:
            row[metric_name] = sample[metric_name]

    return row


def _sample_row_full(sample: dict) -> dict:
    """Full JSONL row: includes all 64 responses and reasoning content."""
    out = copy.deepcopy(sample)
    for key in ("doc_hash", "prompt_hash", "target_hash"):
        out.pop(key, None)
    prompt, gen_kwargs = _extract_prompt_and_gen_kwargs(out.get("arguments"))
    out["prompt"] = prompt
    out["target"] = str(out.get("target", ""))
    out.pop("arguments", None)
    if gen_kwargs is not None:
        out["gen_kwargs"] = gen_kwargs
    out["resps"] = sanitize_list(out["resps"])
    out["filtered_resps"] = sanitize_list(out["filtered_resps"])
    if "reasoning_content" in out:
        out["reasoning_content"] = sanitize_list(out["reasoning_content"])
    return out


def _write_samples_jsonl(
    output_path: str,
    task_name: str,
    rows: list,
    save_all: bool,
) -> None:
    """Write per-sample JSONL. Compact by default, full with --save-all-samples."""
    os.makedirs(output_path, exist_ok=True)
    date_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filepath = os.path.join(output_path, f"samples_{task_name}_{date_id}.jsonl")
    row_fn = _sample_row_full if save_all else _sample_row_compact
    with open(filepath, "w", encoding="utf-8") as f:
        for sample in rows:
            row = row_fn(sample)
            f.write(
                json.dumps(row, default=handle_non_serializable, ensure_ascii=False)
                + "\n"
            )
    logger.info("Wrote %d samples to %s", len(rows), filepath)


# ── Core evaluation ──────────────────────────────────────────────────


def run_single_eval(
    *,
    include_path: str,
    task_name: str,
    model_id: str,
    model_display_name: str,
    output_path: str,
    base_url: str,
    num_concurrent: int,
    num_fewshot: int,
    apply_chat_template: bool,
    log_samples: bool,
    gen_kwargs: str | None = None,
    save_all_samples: bool = False,
    limit: int | None = None,
    cache_requests: str | None = "true",
) -> dict | None:
    """Run a single lm_eval evaluation and return results."""
    _ensure_lm_eval_api_key()
    model_args = f"model={model_id},base_url={base_url},num_concurrent={num_concurrent}"

    results = lm_eval.simple_evaluate(
        model="local-chat-completions",
        model_args=model_args,
        tasks=[task_name],
        num_fewshot=num_fewshot,
        log_samples=log_samples,
        task_manager=lm_eval.tasks.TaskManager(include_path=[include_path]),
        apply_chat_template=apply_chat_template if apply_chat_template else None,
        gen_kwargs=gen_kwargs,
        limit=limit,
        cache_requests=cache_requests,
    )

    if results and log_samples and results.get("samples"):
        _add_reasoning_content_to_samples(results["samples"])

    if results and output_path:
        os.makedirs(output_path, exist_ok=True)

        results_file = os.path.join(output_path, "results.json")
        dumped = {k: v for k, v in results.items() if k != "samples"}
        with open(results_file, "w") as f:
            json.dump(dumped, f, indent=2, default=str)

        if log_samples and "samples" in results:
            for tname, rows in results["samples"].items():
                _write_samples_jsonl(output_path, tname, rows, save_all_samples)

    return results


def main():
    parser = argparse.ArgumentParser(description="Run lm-eval from TOML config")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to TOML config")
    parser.add_argument("--models", nargs="*", help="Filter to specific model name(s)")
    parser.add_argument("--tasks", nargs="*", help="Filter to specific task/group name(s)")
    parser.add_argument("--dry-run", action="store_true", help="Print params without running")
    parser.add_argument(
        "--gen-kwargs",
        type=str,
        default=None,
        help='Comma-separated gen params, e.g. "max_gen_toks=8192,temperature=0.6"',
    )
    parser.add_argument(
        "--num-concurrent",
        type=int,
        default=None,
        metavar="N",
        help="Override parallel in-flight API requests",
    )
    parser.add_argument(
        "--save-all-samples",
        action="store_true",
        default=False,
        help="Save all 64 raw responses per sample in JSONL (default: compact majority-vote only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only evaluate on the first N samples per task (useful for testing)",
    )
    parser.add_argument(
        "--cache-requests",
        type=str,
        default="true",
        choices=["true", "false", "refresh", "delete"],
        help='Cache API responses: "true" reuses cache, "false" disables caching (use for sampling), "refresh" rebuilds, "delete" clears (default: true)',
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    defaults = cfg["defaults"]
    models = cfg["models"]
    tasks = cfg["tasks"]

    if args.models:
        filter_set = {m.lower() for m in args.models}
        models = [m for m in models if m["name"].lower() in filter_set]
        if not models:
            print(f"No models matched: {args.models}", file=sys.stderr)
            sys.exit(1)

    if args.tasks:
        filter_set = {t.lower() for t in args.tasks}
        matched = [t for t in tasks if t["name"].lower() in filter_set]
        if matched:
            tasks = matched
        else:
            tasks = [{"name": n} for n in args.tasks]

    total = len(models) * len(tasks)
    print(f"Running {len(models)} model(s) x {len(tasks)} task(s) = {total} eval(s)\n")

    failures = 0

    for i, model in enumerate(models, 1):
        for j, task in enumerate(tasks, 1):
            run_idx = (i - 1) * len(tasks) + j
            output_path = os.path.join(
                defaults.get("output_path", "output/results"),
                model["name"],
                task["name"],
            )

            gen_kwargs = args.gen_kwargs or model.get("gen_kwargs")
            num_concurrent = (
                args.num_concurrent
                if args.num_concurrent is not None
                else defaults.get("num_concurrent", 5)
            )

            cache_val = args.cache_requests if args.cache_requests != "false" else None

            eval_kwargs = dict(
                include_path=SCRIPT_DIR,
                task_name=task["name"],
                model_id=model["model_id"],
                model_display_name=model["name"],
                output_path=output_path,
                base_url=defaults["base_url"],
                num_concurrent=num_concurrent,
                num_fewshot=defaults.get("num_fewshot", 0),
                apply_chat_template=defaults.get("apply_chat_template", True),
                log_samples=defaults.get("log_samples", True),
                gen_kwargs=gen_kwargs,
                save_all_samples=args.save_all_samples,
                limit=args.limit,
                cache_requests=cache_val,
            )

            header = f"[{run_idx}/{total}] {model['name']} x {task['name']}"
            print(f"{'─' * 60}")
            print(f"  {header}")
            print(f"  -> params: {eval_kwargs}")
            print(f"{'─' * 60}")

            if args.dry_run:
                continue

            try:
                results = run_single_eval(**eval_kwargs)
                if results:
                    print(make_table(results))
                print(f"\n  DONE: {header}\n")
            except Exception:
                traceback.print_exc()
                print(f"\n  FAILED: {header}\n", file=sys.stderr)
                failures += 1

    if failures:
        print(f"\n{failures}/{total} evaluation(s) failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
