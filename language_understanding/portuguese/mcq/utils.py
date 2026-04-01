"""Utility helpers for Portuguese MCQ tasks (ENEM, BLUEX, OAB)."""


def generate_options(choices):
    """Format choices dict (text + label lists) into lettered options."""
    options = ""
    for text, label in zip(choices["text"], choices["label"]):
        options += f"{label}. {text}\n"
    return options.strip()


def enem_doc_to_text(doc):
    """Prompt for ENEM / BLUEX multiple-choice questions."""
    return (
        "Selecione a alternativa correta e responda apenas com a letra "
        "correspondente (A, B, C, D ou E).\n\n"
        f"Pergunta:\n{doc['question']}\n"
        f"Alternativas:\n{generate_options(doc['choices'])}\n"
        "Resposta correta:"
    )


def oab_doc_to_text(doc):
    """Prompt for OAB (Brazilian Bar Exam) multiple-choice questions."""
    return (
        "Selecione a alternativa correta e responda apenas com a letra "
        "correspondente (A, B, C ou D).\n\n"
        f"Questão:\n{doc['question']}\n"
        f"Alternativas:\n{generate_options(doc['choices'])}\n"
        "Resposta correta:"
    )
