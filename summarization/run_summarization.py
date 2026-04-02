#!/usr/bin/env python3
"""Summarization faithfulness benchmark.

Evaluates an LLM's ability to produce faithful summaries of domain-specific
Brazilian Portuguese texts without inserting hallucinated information.

Pipeline:
  1. Load 15 source texts (5 Legal, 5 Medical, 5 Financial) from source_texts.json
  2. Ask the target model to summarize each text (bare user message, no system prompt)
  3. Use an LLM judge (default: gpt-5.2) to verify faithfulness
  4. Compute Faithfulness Rate and per-domain breakdowns

Metrics:
  Faithfulness Rate  % of summaries with zero hallucinations
  Per-domain         Faithfulness broken down by Jurídico / Médico / Financeiro

Usage:
    # Quick test (3 texts)
    python run_summarization.py --base-url http://localhost:8000/v1 \\
        --model my-model --limit 3

    # Full benchmark with LLM judge
    python run_summarization.py --base-url http://localhost:8000/v1 \\
        --model my-model \\
        --judge-base-url https://api.openai.com/v1 \\
        --judge-api-key $OPENAI_API_KEY

    # Using OpenRouter for both generation and judging
    python run_summarization.py --base-url https://openrouter.ai/api/v1 \\
        --model meetkai/functionary-pt-BR-v1.1 \\
        --judge-model openai/gpt-5.2
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from tqdm import tqdm

logger = logging.getLogger(__name__)

SOURCE_TEXTS_PATH = Path(__file__).parent / "source_texts.json"

SUMMARIZATION_PROMPT = (
    "Resuma o texto abaixo de forma concisa e precisa. "
    "Inclua apenas informações presentes no texto original.\n\n"
    "Texto:\n{source_text}"
)

JUDGE_SYSTEM_PROMPT = """\
You are a faithfulness evaluator for text summaries. You will receive an \
ORIGINAL TEXT and a SUMMARY produced by a language model.

Your task: determine whether the SUMMARY contains ONLY information that is \
present in or directly inferable from the ORIGINAL TEXT.

Rules:
- UNFAITHFUL if the summary states facts, numbers, names, dates, \
recommendations, or conclusions NOT found in the original text.
- Paraphrasing or reorganizing information from the source is acceptable.
- Omitting information is acceptable (not a hallucination).
- Adding general knowledge, inferences, or plausible-sounding details NOT \
stated in the source IS a hallucination.

Respond with ONLY a JSON object (no markdown fences):
{"faithful": true, "hallucinations": []}
or
{"faithful": false, "hallucinations": ["first fabricated claim", "second fabricated claim"]}"""

JUDGE_USER_TEMPLATE = """\
ORIGINAL TEXT:
{source_text}

SUMMARY:
{summary}

Is every claim in the SUMMARY supported by the ORIGINAL TEXT? Return JSON."""


# ── Judge ─────────────────────────────────────────────────────────────


class FaithfulnessJudge:
    """LLM-as-judge for summary faithfulness scoring."""

    def __init__(self, client: OpenAI, model: str):
        self._client = client
        self._model = model

    def evaluate(self, source_text: str, summary: str) -> dict:
        """Return {"faithful": bool, "hallucinations": [...]}."""
        user_msg = JUDGE_USER_TEMPLATE.format(
            source_text=source_text,
            summary=summary,
        )
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        for attempt in range(3):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=1024,
                )
                text = (resp.choices[0].message.content or "").strip()
                parsed = self._parse_json(text)
                if parsed is not None:
                    return parsed
                logger.warning(
                    "Judge parse failure (attempt %d/3): %s",
                    attempt + 1, text[:300],
                )
            except Exception as exc:
                logger.warning(
                    "Judge API error (attempt %d/3): %s", attempt + 1, exc
                )

        return {
            "faithful": False,
            "hallucinations": ["[JUDGE PARSE FAILURE — defaulted to unfaithful]"],
        }

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None

        if "faithful" not in data:
            return None

        return {
            "faithful": bool(data["faithful"]),
            "hallucinations": data.get("hallucinations", []) or [],
        }

    @property
    def name(self) -> str:
        return f"faithfulness_judge ({self._model})"


def build_judge(args: argparse.Namespace) -> FaithfulnessJudge:
    judge_key = (
        args.judge_api_key
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("OPENROUTER_API_KEY", "")
    )
    if not judge_key:
        sys.exit(
            "LLM judge requires an API key.\n"
            "Set OPENAI_API_KEY / OPENROUTER_API_KEY or pass --judge-api-key."
        )
    judge_base = args.judge_base_url or "https://api.openai.com/v1"
    judge_client = OpenAI(api_key=judge_key, base_url=judge_base)
    return FaithfulnessJudge(judge_client, args.judge_model)


# ── Model generation ─────────────────────────────────────────────────


def generate_summary(
    client: OpenAI,
    source_text: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Generate a summary with no system prompt (bare user message)."""
    prompt = SUMMARIZATION_PROMPT.format(source_text=source_text)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            n=1,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("Generation error: %s", exc)
        return ""


# ── Metrics ──────────────────────────────────────────────────────────


def compute_metrics(samples: list[dict]) -> dict:
    total = len(samples)
    if total == 0:
        return {}

    faithful_count = sum(1 for s in samples if s["faithful"])
    faithfulness_rate = round(faithful_count / total, 4)

    domain_metrics = _domain_breakdown(samples)

    return {
        "faithfulness_rate": faithfulness_rate,
        "faithful_count": faithful_count,
        "unfaithful_count": total - faithful_count,
        "total": total,
        "per_domain": domain_metrics,
    }


def _domain_breakdown(samples: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        groups[s["domain"]].append(s)

    result = {}
    for domain, items in sorted(groups.items()):
        faithful = sum(1 for s in items if s["faithful"])
        total = len(items)
        result[domain] = {
            "faithfulness_rate": round(faithful / total, 4),
            "faithful": faithful,
            "unfaithful": total - faithful,
            "total": total,
        }
    return result


# ── Main ─────────────────────────────────────────────────────────────


def load_source_texts(path: Path, limit: int | None = None) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        texts = json.load(f)
    if limit:
        texts = texts[:limit]
    return texts


def run_benchmark(args: argparse.Namespace) -> dict:
    api_key = (
        args.api_key
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("OPENROUTER_API_KEY", "")
    )
    if not api_key:
        sys.exit("Model API key required. Set OPENAI_API_KEY or use --api-key.")

    client = OpenAI(api_key=api_key, base_url=args.base_url)
    judge = build_judge(args)

    source_path = Path(args.source_texts) if args.source_texts else SOURCE_TEXTS_PATH
    texts = load_source_texts(source_path, args.limit)
    logger.info(
        "Evaluating %d texts | model: %s | judge: %s",
        len(texts), args.model, judge.name,
    )

    os.makedirs(args.output_dir, exist_ok=True)
    samples_path = os.path.join(args.output_dir, "samples.jsonl")

    def _process_item(item: dict) -> dict:
        summary = generate_summary(
            client,
            item["source_text"],
            model=args.model,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        verdict = judge.evaluate(item["source_text"], summary)

        return {
            "id": item["id"],
            "domain": item["domain"],
            "title": item["title"],
            "source_text": item["source_text"],
            "summary": summary,
            "faithful": verdict["faithful"],
            "hallucinations": verdict["hallucinations"],
        }

    results_in_order: list[dict | None] = [None] * len(texts)

    with ThreadPoolExecutor(max_workers=args.num_concurrent) as executor:
        future_to_idx = {
            executor.submit(_process_item, texts[i]): i
            for i in range(len(texts))
        }
        for future in tqdm(
            as_completed(future_to_idx), total=len(texts), desc="Summarizing"
        ):
            idx = future_to_idx[future]
            try:
                results_in_order[idx] = future.result()
            except Exception as exc:
                logger.error("Error processing item %d: %s", idx, exc)

    all_samples = [s for s in results_in_order if s is not None]

    with open(samples_path, "w", encoding="utf-8") as f:
        for sample in all_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    metrics = compute_metrics(all_samples)

    results = {
        "metrics": metrics,
        "config": {
            "model": args.model,
            "base_url": args.base_url,
            "judge": judge.name,
            "num_texts": len(all_samples),
            "num_concurrent": args.num_concurrent,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "source_texts": str(source_path),
            "methodology": "Summarization faithfulness evaluation — LLM judge "
                           "verifies each summary contains only information "
                           "present in the source text.",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    results_path = os.path.join(args.output_dir, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    _print_summary(metrics, args, judge)
    print(f"\n  Results: {results_path}")
    print(f"  Samples: {samples_path}")

    return results


def _print_summary(
    metrics: dict, args: argparse.Namespace, judge: FaithfulnessJudge
) -> None:
    m = metrics
    print(f"\n{'=' * 60}")
    print("  Summarization Faithfulness Benchmark Results")
    print(f"{'=' * 60}")
    print(f"  Model:                  {args.model}")
    print(f"  Judge:                  {judge.name}")
    print(f"  Texts evaluated:        {m['total']}")
    print(f"{'─' * 60}")
    print(f"  FAITHFULNESS RATE:      {m['faithfulness_rate']:.2%}")
    print(f"  Faithful summaries:     {m['faithful_count']}")
    print(f"  Unfaithful summaries:   {m['unfaithful_count']}")
    print(f"{'─' * 60}")

    print("\n  Per Domain:")
    for domain, info in sorted(m["per_domain"].items()):
        print(
            f"    {domain:20s}  "
            f"faithfulness={info['faithfulness_rate']:.2%}  "
            f"({info['faithful']}/{info['total']})"
        )

    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description="Summarization faithfulness benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    gen = parser.add_argument_group("Generation (target model)")
    gen.add_argument(
        "--base-url", required=True,
        help="OpenAI-compatible API base URL",
    )
    gen.add_argument("--model", required=True, help="Model ID sent to the API")
    gen.add_argument(
        "--api-key", default=None,
        help="Model API key (or set OPENAI_API_KEY)",
    )
    gen.add_argument(
        "--temperature", type=float, default=0.0,
        help="Sampling temperature (default: 0.0)",
    )
    gen.add_argument(
        "--max-tokens", type=int, default=8192,
        help="Max tokens per summary (default: 8192)",
    )
    gen.add_argument(
        "--limit", type=int, default=None,
        help="Only evaluate first N texts (for testing)",
    )
    gen.add_argument(
        "--num-concurrent", type=int, default=1,
        help="Parallel requests (default: 1)",
    )

    jdg = parser.add_argument_group("Judge (faithfulness evaluator)")
    jdg.add_argument(
        "--judge-model", default="gpt-5.2",
        help="Judge model ID (default: gpt-5.2)",
    )
    jdg.add_argument(
        "--judge-base-url", default=None,
        help="Judge API base URL (default: https://api.openai.com/v1)",
    )
    jdg.add_argument(
        "--judge-api-key", default=None,
        help="Judge API key (defaults to OPENAI_API_KEY)",
    )

    parser.add_argument(
        "--output-dir", default="output/summarization",
        help="Output directory (default: output/summarization)",
    )
    parser.add_argument(
        "--source-texts", default=None,
        help="Path to source_texts.json (default: bundled file)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    run_benchmark(args)


if __name__ == "__main__":
    main()
