"""Utility helpers for the GSM8K mathematical reasoning task."""

import re


def doc_to_text(doc):
    """Format a GSM8K sample as a step-by-step math prompt.

    Dataset fields (openai/gsm8k, main):
        question – the math word problem
        answer   – full chain-of-thought ending with ``#### N``
    """
    return (
        "Solve the following math problem step by step. "
        'After your reasoning, provide the final numerical answer on a new line prefixed with "#### ".\n\n'
        f"Question:\n{doc['question']}\n\n"
        "Answer:"
    )


def doc_to_target(doc):
    """Return the gold-standard numerical answer extracted from ``#### N``."""
    answer = doc["answer"]
    match = re.search(r"####\s*(.+)", answer)
    if match:
        return match.group(1).strip().replace(",", "")
    return answer.strip()
