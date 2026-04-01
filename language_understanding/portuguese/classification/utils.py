"""Utility helpers for Portuguese classification tasks (generative mode)."""

import os as _os, sys as _sys  # noqa: E401
_sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(__file__), "..", "..")))

from f1_utils import macro_f1_agg, process_results_f1  # noqa: F401


SENTIMENT_LABEL_MAP = {
    "Positive": "Positivo",
    "Negative": "Negativo",
    "Neutral": "Neutro",
}


def process_binary_docs(dataset):
    """Map 0/1 label -> Nao/Sim (for hatebr, portuguese_hate_speech)."""

    def _map(doc):
        doc["target"] = "Sim" if doc["label"] == 1 else "Não"
        return doc

    return dataset.map(_map)


def process_sentiment_docs(dataset):
    """Map Positive/Negative/Neutral -> Positivo/Negativo/Neutro (tweetsentbr)."""

    def _map(doc):
        doc["target"] = SENTIMENT_LABEL_MAP.get(doc["label"], "Neutro")
        return doc

    return dataset.map(_map)


def process_results(doc, results):
    """Return (pred, gold) tuple for macro-F1 aggregation."""
    return process_results_f1(doc, results)
