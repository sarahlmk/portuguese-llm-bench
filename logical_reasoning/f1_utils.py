"""Shared macro-F1 utilities and custom filters for Portuguese evaluation.

Provides:
- macro-averaged F1 aggregation and process_results helper
- ``regex_last``: like lm_eval's ``regex`` filter, but picks a match
  from ``findall`` using ``group_select``; default ``group_select=-1`` is the
  **last** match (needed when CoT/reasoning mentions labels before the answer).
- ``median_float_vote``: aggregates repeated float responses by taking the
  median (used for STS tasks where majority_vote is not applicable).
"""

import re

from lm_eval.api.filter import Filter
from lm_eval.api.registry import register_filter


def _strip_think_tags(text: str) -> str:
    """Strip <think>...</think> reasoning wrapper (e.g. Qwen thinking models)."""
    if "</think>" in text:
        return text.split("</think>")[-1].strip()
    return text


@register_filter("strip_think_recover")
class StripThinkRecoverFilter(Filter):
    """Remove ``<think>…</think>`` wrapper, recovering from empty content.

    Thinking models often return the answer inside ``reasoning_content``
    with an empty ``content`` field (the stop sequence ``\\n\\n`` fires
    immediately).  The built-in ``strip_think`` simply deletes the block,
    leaving an empty string for those cases.

    This filter:
    1. Uses content after ``</think>`` when it is non-empty (normal case).
    2. Falls back to the **last non-empty line** of the reasoning when
       content is empty — the model's conclusion almost always appears
       there, making downstream regex extraction succeed.
    """

    def __init__(self) -> None:
        pass

    def apply(self, resps, docs):
        def strip_set(inst):
            stripped = []
            for resp in inst:
                if not isinstance(resp, str):
                    resp = ""
                content = _strip_think_tags(resp)
                if not content and "</think>" in resp:
                    reasoning = resp.split("</think>")[0]
                    if "<think>" in reasoning:
                        reasoning = reasoning.split("<think>", 1)[1]
                    lines = [ln.strip() for ln in reasoning.strip().splitlines() if ln.strip()]
                    content = lines[-1] if lines else ""
                stripped.append(content)
            return stripped

        return list(map(strip_set, resps))


def macro_f1_agg(items):
    """Compute macro-averaged F1 over all class labels.

    ``items`` is a list of ``(pred, gold)`` tuples per document.
    """
    preds = [item[0] for item in items]
    golds = [item[1] for item in items]

    all_labels = sorted(set(golds))

    f1_scores = []
    for label in all_labels:
        tp = sum(1 for p, g in zip(preds, golds) if p == label and g == label)
        fp = sum(1 for p, g in zip(preds, golds) if p == label and g != label)
        fn = sum(1 for p, g in zip(preds, golds) if p != label and g == label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        f1_scores.append(f1)

    return sum(f1_scores) / len(f1_scores) if f1_scores else 0.0


@register_filter("regex_last")
class RegexLastFilter(Filter):
    """Regex extraction; ``group_select=-1`` uses the last ``findall`` hit."""

    def __init__(
        self,
        regex_pattern: str = r"#### (\-?[0-9\.\,]+)",
        group_select: int = -1,
        fallback: str = "[invalid]",
    ) -> None:
        self.regex = re.compile(regex_pattern)
        self.group_select = group_select
        self.fallback = fallback

    def apply(self, resps: list[list[str]], docs: list[dict]) -> list[list[str]]:
        def filter_set(inst):
            filtered = []
            for resp in inst:
                if not isinstance(resp, str):
                    resp = ""
                matches = self.regex.findall(resp)
                if not matches:
                    filtered.append(self.fallback)
                    continue
                if self.group_select >= 0:
                    idx = min(self.group_select, len(matches) - 1)
                else:
                    idx = max(0, len(matches) + self.group_select)
                match = matches[idx]
                if isinstance(match, tuple):
                    match = [m for m in match if m]
                    if match:
                        match = match[0]
                    else:
                        match = self.fallback
                match = str(match).strip()
                filtered.append(match)
            return filtered

        return list(map(filter_set, resps))


@register_filter("median_float_vote")
class MedianFloatVoteFilter(Filter):
    """Aggregate repeated float responses by taking the median.

    Designed for STS tasks with ``repeats > 1``: parses each response as a
    float (handles Portuguese comma notation), clamps to [1.0, 5.0], and
    returns the median formatted as a Portuguese decimal string.
    """

    def __init__(
        self,
        regex_pattern: str = r"(\d+[,.]?\d*)",
        clamp_min: float = 1.0,
        clamp_max: float = 5.0,
        default: float = 3.0,
    ) -> None:
        self.regex = re.compile(regex_pattern)
        self.clamp_min = clamp_min
        self.clamp_max = clamp_max
        self.default = default

    def apply(self, resps, docs):
        def select_median(resp_list):
            values = []
            for resp in resp_list:
                if not isinstance(resp, str):
                    resp = str(resp) if resp else ""
                match = self.regex.search(resp)
                if match:
                    num_str = match.group(1).replace(",", ".")
                    try:
                        val = float(num_str)
                        val = max(self.clamp_min, min(self.clamp_max, val))
                        values.append(val)
                    except ValueError:
                        pass
            if not values:
                return ["{:.1f}".format(self.default).replace(".", ",")]
            values.sort()
            n = len(values)
            if n % 2 == 1:
                median = values[n // 2]
            else:
                median = (values[n // 2 - 1] + values[n // 2]) / 2
            return ["{:.1f}".format(median).replace(".", ",")]

        return list(map(select_median, resps))


@register_filter("trimmed_mean_float_vote")
class TrimmedMeanFloatVoteFilter(Filter):
    """Aggregate repeated float responses via trimmed mean.

    Drops the top and bottom ``trim_pct`` of extracted values, then averages
    the rest.  More robust than plain mean (outlier-resistant) while
    preserving fine-grained predictions (unlike median which quantizes).
    """

    def __init__(
        self,
        regex_pattern: str = r"(\d+[,.]?\d*)",
        clamp_min: float = 1.0,
        clamp_max: float = 5.0,
        default: float = 3.0,
        trim_pct: float = 0.1,
    ) -> None:
        self.regex = re.compile(regex_pattern)
        self.clamp_min = clamp_min
        self.clamp_max = clamp_max
        self.default = default
        self.trim_pct = trim_pct

    def apply(self, resps, docs):
        def aggregate(resp_list):
            values = []
            for resp in resp_list:
                if not isinstance(resp, str):
                    resp = str(resp) if resp else ""
                match = self.regex.search(resp)
                if match:
                    num_str = match.group(1).replace(",", ".")
                    try:
                        val = float(num_str)
                        val = max(self.clamp_min, min(self.clamp_max, val))
                        values.append(val)
                    except ValueError:
                        pass
            if not values:
                return ["{:.2f}".format(self.default).replace(".", ",")]
            values.sort()
            n = len(values)
            trim_n = max(1, int(n * self.trim_pct))
            trimmed = values[trim_n : n - trim_n] if n > 2 * trim_n else values
            mean_val = sum(trimmed) / len(trimmed)
            return ["{:.2f}".format(mean_val).replace(".", ",")]

        return list(map(aggregate, resps))


_STS_SCORE_RE = re.compile(
    r"(?:"
    r"[Rr]esposta[:\s]*\**\s*(\d+[,.]\d+)"   # "Resposta: 4,5" or "**Resposta:** 4.5"
    r"|[Pp]ontua[çc][ãa]o[:\s]*\**\s*(\d+[,.]\d+)"  # "Pontuação: 3,0"
    r"|\*\*(\d+[,.]\d+)\*\*"                  # "**4,5**"
    r"|(\d+[,.]\d+)\s*/\s*5"                  # "4,5/5" or "4.5/5.0"
    r")",
)
_FALLBACK_FLOAT_RE = re.compile(r"(\d+[,.]\d+)")


@register_filter("sts_score_extract")
class StsScoreExtractFilter(Filter):
    """Extract a float score from the full response for STS tasks.

    Handles thinking models where the score lives inside ``<think>`` tags:
    1. Try content after ``</think>`` first.
    2. Search the full text for explicit score patterns
       (``Resposta: X,X``, ``**X,X**``, ``X,X/5``).
    3. Fall back to the last decimal number in [1, 5] range.

    Returns the extracted score as a Portuguese-format string (e.g. "4,5").
    """

    def __init__(self, clamp_min: float = 1.0, clamp_max: float = 5.0, default: float = 3.0) -> None:
        self.clamp_min = clamp_min
        self.clamp_max = clamp_max
        self.default = default

    def _parse(self, raw: str) -> float:
        for m in raw.replace(",", "."), raw:
            pass

        content = _strip_think_tags(raw)
        if content:
            score = self._try_extract(content)
            if score is not None:
                return score

        score = self._try_pattern(raw)
        if score is not None:
            return score

        score = self._try_last_decimal(raw)
        if score is not None:
            return score

        return self.default

    def _try_extract(self, text: str) -> float | None:
        m = _FALLBACK_FLOAT_RE.search(text)
        if m:
            val = float(m.group(1).replace(",", "."))
            if self.clamp_min <= val <= self.clamp_max:
                return val
        return None

    def _try_pattern(self, text: str) -> float | None:
        matches = list(_STS_SCORE_RE.finditer(text))
        if not matches:
            return None
        last = matches[-1]
        for g in last.groups():
            if g is not None:
                val = float(g.replace(",", "."))
                return max(self.clamp_min, min(self.clamp_max, val))
        return None

    def _try_last_decimal(self, text: str) -> float | None:
        matches = _FALLBACK_FLOAT_RE.findall(text)
        for m in reversed(matches):
            val = float(m.replace(",", "."))
            if self.clamp_min <= val <= self.clamp_max:
                return val
        return None

    def apply(self, resps, docs):
        def extract_set(inst):
            results = []
            for resp in inst:
                if not isinstance(resp, str):
                    resp = ""
                val = self._parse(resp)
                results.append("{:.1f}".format(val).replace(".", ","))
            return results

        return list(map(extract_set, resps))


def process_results_f1(doc, results, *, gold_key="target"):
    """Return ``(pred, gold)`` for macro-F1 aggregation.

    ``pred`` is the label after stripping think wrappers.
    """
    raw_response = results[0].strip() if results[0] else ""
    pred = _strip_think_tags(raw_response)
    gold = doc.get(gold_key, "").strip()
    return {"f1_macro": (pred, gold)}
