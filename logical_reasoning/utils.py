"""Utility helpers for the LogiQA logical reasoning task."""

LABEL_MAP = {"a": "A", "b": "B", "c": "C", "d": "D"}


def doc_to_text(doc):
    """Format a LogiQA sample as a multiple-choice prompt.

    Dataset fields (EleutherAI/logiqa):
        context  – background passage
        question – the reasoning question
        options  – list of four answer strings
        label    – correct answer as lowercase letter (a/b/c/d)
    """
    choices = ["A", "B", "C", "D"]
    prompt = (
        "Read the following passage and answer the question by selecting "
        "the correct option. Reply with only the letter (A, B, C, or D).\n\n"
        f"Passage:\n{doc['context']}\n\n"
        f"Question:\n{doc['question']}\n\n"
        "Choices:\n"
    )
    for letter, option in zip(choices, doc["options"]):
        prompt += f"{letter}. {option}\n"
    prompt += "\nAnswer:"
    return prompt


def doc_to_target(doc):
    """Return the gold-standard answer as an uppercase letter."""
    return LABEL_MAP.get(doc["label"].strip().lower(), doc["label"].strip().upper())
