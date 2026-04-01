"""Utility helpers for Portuguese NLI / STS tasks (generative mode)."""

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(__file__), "..", "..")))

import math
import re

from f1_utils import macro_f1_agg, process_results_f1  # noqa: F401


def process_assin2_rte_docs(dataset):
    """Map entailment_judgment 0/1 -> Nao/Sim."""

    def _map(doc):
        doc["target"] = "Sim" if doc["entailment_judgment"] == 1 else "Não"
        return doc

    return dataset.map(_map)


def process_faquad_nli_docs(dataset):
    """Map label 0/1 -> Nao/Sim."""

    def _map(doc):
        doc["target"] = "Sim" if doc["label"] == 1 else "Não"
        return doc

    return dataset.map(_map)


def process_nli_results(doc, results):
    """Return (pred, gold) tuple for macro-F1 aggregation."""
    return process_results_f1(doc, results)


def assin2_float_to_pt_str(doc):
    """Format relatedness_score as a Portuguese-style decimal string (comma)."""
    return "{:.1f}".format(doc["relatedness_score"]).replace(".", ",")


def _extract_float(text):
    """Extract a float value from text, handling Portuguese comma notation."""
    text = text.strip()
    match = re.search(r"(\d+[,.]?\d*)", text)
    if match:
        num_str = match.group(1).replace(",", ".")
        try:
            val = float(num_str)
            return max(1.0, min(5.0, val))
        except ValueError:
            pass
    return 3.0


def process_sts_results(doc, results):
    """Extract predicted float and pair with gold for pearson/mse."""
    pred_text = results[0].strip() if results[0] else ""
    pred_val = _extract_float(pred_text)
    gold_val = doc["relatedness_score"]
    return {
        "pearson": (pred_val, gold_val),
        "mse": (pred_val, gold_val),
    }


def pearson_agg(items):
    """Compute Pearson correlation coefficient."""
    preds = [item[0] for item in items]
    golds = [item[1] for item in items]
    n = len(preds)
    if n < 2:
        return 0.0
    mean_p = sum(preds) / n
    mean_g = sum(golds) / n
    cov = sum((p - mean_p) * (g - mean_g) for p, g in zip(preds, golds)) / n
    std_p = math.sqrt(sum((p - mean_p) ** 2 for p in preds) / n)
    std_g = math.sqrt(sum((g - mean_g) ** 2 for g in golds) / n)
    if std_p * std_g == 0:
        return 0.0
    return cov / (std_p * std_g)


def mse_agg(items):
    """Compute mean squared error."""
    preds = [item[0] for item in items]
    golds = [item[1] for item in items]
    return sum((p - g) ** 2 for p, g in zip(preds, golds)) / len(preds)
