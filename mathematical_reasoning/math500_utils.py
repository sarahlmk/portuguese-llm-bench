"""Utility helpers for the MATH-500 mathematical reasoning task.

Adapted from the upstream lm-evaluation-harness minerva_math/utils.py with:
- Chat-friendly prompt asking for \\boxed{} answers
- <think>...</think> tag stripping for reasoning models
- Dual metric: exact_match (normalized string + SymPy) and math_verify
"""

import logging
import re
import signal
from typing import Optional

import datasets

logger = logging.getLogger(__name__)

try:
    import sympy
    from sympy.parsing.latex import parse_latex

    _HAS_SYMPY = True
except ImportError:
    _HAS_SYMPY = False

try:
    from math_verify import parse, verify

    _HAS_MATH_VERIFY = True
except ImportError:
    _HAS_MATH_VERIFY = False


_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def _strip_think_tags(text: str) -> str:
    """Strip <think>...</think> reasoning wrapper."""
    if _THINK_CLOSE in text:
        return text.split(_THINK_CLOSE)[-1].strip()
    return text


def doc_to_text(doc: dict) -> str:
    return (
        "Solve the following math problem step by step. "
        "Present your final answer enclosed in \\boxed{}.\n\n"
        f"Problem:\n{doc['problem']}\n\n"
        "Solution:"
    )


def process_docs(dataset: datasets.Dataset) -> datasets.Dataset:
    def _process_doc(doc: dict) -> dict:
        out_doc = {
            "problem": doc["problem"],
            "solution": doc["solution"],
            "answer": normalize_final_answer(
                remove_boxed(last_boxed_only_string(doc["solution"]) or "")
            ),
        }
        if getattr(doc, "few_shot", None) is not None:
            out_doc["few_shot"] = True
        return out_doc

    return dataset.map(_process_doc)


def process_results(doc: dict, results: list[str]) -> dict[str, int]:
    raw = results[0] if results[0] else ""
    candidates = _strip_think_tags(raw)

    unnormalized_answer = get_unnormalized_answer(candidates)
    answer = normalize_final_answer(unnormalized_answer)

    if is_equiv(answer, doc["answer"]):
        retval = 1
    else:
        retval = 0

    mathval = 0
    if _HAS_MATH_VERIFY:
        try:
            _mvres = verify(
                gold=parse(doc["solution"]),
                target=parse(candidates),
            )
            mathval = 1 if _mvres else 0
        except Exception:
            mathval = 0

    return {
        "exact_match": retval,
        "math_verify": mathval,
    }


# ── Boxed-answer extraction (from Lewkowycz et al., 2022) ───────────


def last_boxed_only_string(string: str) -> Optional[str]:
    idx = string.rfind("\\boxed")
    if "\\boxed " in string:
        return "\\boxed " + string.split("\\boxed ")[-1].split("$")[0]
    if idx < 0:
        idx = string.rfind("\\fbox")
        if idx < 0:
            return None

    i = idx
    right_brace_idx = None
    num_left_braces_open = 0
    while i < len(string):
        if string[i] == "{":
            num_left_braces_open += 1
        if string[i] == "}":
            num_left_braces_open -= 1
            if num_left_braces_open == 0:
                right_brace_idx = i
                break
        i += 1

    if right_brace_idx is None:
        return None
    return string[idx : right_brace_idx + 1]


def remove_boxed(s: str) -> str:
    if not s:
        return ""
    if "\\boxed " in s:
        left = "\\boxed "
        if s[: len(left)] == left:
            return s[len(left) :]
    left = "\\boxed{"
    if s.startswith(left) and s.endswith("}"):
        return s[len(left) : -1]
    return s


# ── Symbolic equivalence ─────────────────────────────────────────────


class _Timeout:
    def __init__(self, seconds=1, error_message="Timeout"):
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.alarm(0)


def is_equiv(x1: str, x2: str) -> bool:
    """Check symbolic equivalence of two normalized LaTeX strings via SymPy."""
    if x1.strip() == x2.strip():
        return True
    if not _HAS_SYMPY:
        return False
    try:
        with _Timeout(seconds=5):
            try:
                parsed_x1 = parse_latex(x1)
                parsed_x2 = parse_latex(x2)
            except (
                sympy.parsing.latex.errors.LaTeXParsingError,
                sympy.SympifyError,
                TypeError,
            ):
                return False
            try:
                diff = parsed_x1 - parsed_x2
            except TypeError:
                return False
            try:
                return sympy.simplify(diff) == 0
            except ValueError:
                return False
    except TimeoutError:
        return False
    except Exception:
        return False


# ── Answer extraction ────────────────────────────────────────────────


def get_unnormalized_answer(text: str) -> str:
    """Extract the final answer from model output.

    Tries (in order):
    1. \\boxed{...} — the format we explicitly request
    2. "Final Answer: The final answer is ..." — upstream Minerva format
    3. Returns "[invalidanswer]" if neither is found
    """
    INVALID = "[invalidanswer]"

    boxed = last_boxed_only_string(text)
    if boxed:
        return remove_boxed(boxed)

    end_seq = "I hope it is correct."
    text_aug = text + end_seq
    match = re.search(
        r"Final Answer: The final answer is(.*?)\. I hope it is correct\.",
        text_aug,
    )
    if match:
        return match.group(1).strip()

    return INVALID


# ── Normalization (Lewkowycz et al., 2022 Appendix D) ────────────────


SUBSTITUTIONS = [
    ("an ", ""),
    ("a ", ""),
    (".$", "$"),
    ("\\$", ""),
    (r"\ ", ""),
    (" ", ""),
    ("mbox", "text"),
    (",\\text{and}", ","),
    ("\\text{and}", ","),
    ("\\text{m}", "\\text{}"),
]

REMOVED_EXPRESSIONS = [
    "square", "ways", "integers", "dollars", "mph", "inches", "ft",
    "hours", "km", "units", "\\ldots", "sue", "points", "feet",
    "minutes", "digits", "cents", "degrees", "cm", "gm", "pounds",
    "meters", "meals", "edges", "students", "childrentickets",
    "multiples", "\\text{s}", "\\text{.}", "\\text{\ns}",
    "\\text{}^2", "\\text{}^3", "\\text{\n}", "\\text{}",
    r"\mathrm{th}", r"^\circ", r"^{\circ}", r"\;", r",\!", "{,}",
    '"', "\\dots",
]


def normalize_final_answer(final_answer: str) -> str:
    """Normalize a final answer to a quantitative reasoning question.

    Copied from appendix D of Lewkowycz et al. (2022).
    """
    final_answer = final_answer.split("=")[-1]

    for before, after in SUBSTITUTIONS:
        final_answer = final_answer.replace(before, after)
    for expr in REMOVED_EXPRESSIONS:
        final_answer = final_answer.replace(expr, "")

    final_answer = re.sub(r"(.*?)(\$)(.*?)(\$)(.*)", "$\\3$", final_answer)
    final_answer = re.sub(r"(\\text\{)(.*?)(\})", "\\2", final_answer)
    final_answer = re.sub(r"(\\textbf\{)(.*?)(\})", "\\2", final_answer)
    final_answer = re.sub(r"(\\overline\{)(.*?)(\})", "\\2", final_answer)
    final_answer = re.sub(r"(\\boxed\{)(.*)(\})", "\\2", final_answer)

    final_answer = re.sub(r"(frac)([^{])(.)", "frac{\\2}{\\3}", final_answer)
    final_answer = re.sub(r"(sqrt)([^{])", "sqrt{\\2}", final_answer)
    final_answer = final_answer.replace("$", "")

    if final_answer.replace(",", "").isdigit():
        final_answer = final_answer.replace(",", "")

    return final_answer
