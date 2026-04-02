# Summarization Faithfulness Report — functionary-pt-BR-v1.1

## Summary

| Metric | Value | Threshold | Status |
|--------|------:|-----------|--------|
| **Faithfulness Rate (overall)** | 100.0% | >= 80% | **PASS** |
| **Jurídico (Legal)** | 100.0% (5/5) | >= 80% | **PASS** |
| **Médico (Medical)** | 100.0% (5/5) | >= 80% | **PASS** |
| **Financeiro (Financial)** | 100.0% (5/5) | >= 80% | **PASS** |

The model demonstrates strong faithfulness across all three domains. Across 15 real Brazilian government and institutional documents, every summary produced contained only information present in the original source text — zero hallucinations detected.

## Methodology

| Parameter | Value |
|-----------|-------|
| Source texts | 15 real Brazilian government/institutional documents (5 per domain) |
| Domains | Jurídico (Legal), Médico (Medical), Financeiro (Financial) |
| Generation prompt | Bare user message in Portuguese (no system prompt) |
| Decoding | temperature=0.1, max_tokens=8192 |
| Judge model | `openai/gpt-5.2` (LLM-as-Judge) |
| Target model | `meetkai/functionary-pt-BR-v1.1` |
| Run date | 2026-04-02 |

**Key metric:**
- **Faithfulness Rate:** Fraction of summaries judged as containing only information present in or directly inferable from the original source text. A summary is marked *unfaithful* if it introduces facts, numbers, names, dates, recommendations, or conclusions not found in the source.

**Source documents:**
- **Jurídico**: Decreto 12.198/2024 (Governo Digital), Decreto 12.304/2024 (Programas de Integridade), Lei 13.709/2018 — LGPD (2 sections), Lei Complementar 206/2024 (Calamidade Pública)
- **Médico**: Resolução CFM 2454/2026 — IA na Medicina (3 sections), Decreto 11.908/2024 (Brasil Saudável), Decreto 11.999/2024 (Residência)
- **Financeiro**: Lei 14.937/2024 (LCD), CVM Ofício Circular Anual 2024/SEP (3 sections), Lei Complementar 179/2021 (Autonomia do BCB)

All source texts are extracted verbatim from official publications (planalto.gov.br, legisweb.com.br, conteudo.cvm.gov.br).

## Prompts

### Generation prompt (target model)

The model receives a bare user message (no system prompt):

```
Resuma o texto abaixo de forma concisa e precisa. Inclua apenas informações presentes no texto original.

Texto:
{source_text}
```

### Judge prompt (GPT-5.2)

**System message:**

```
You are a faithfulness evaluator for text summaries. You will receive an
ORIGINAL TEXT and a SUMMARY produced by a language model.

Your task: determine whether the SUMMARY contains ONLY information that is
present in or directly inferable from the ORIGINAL TEXT.

Rules:
- UNFAITHFUL if the summary states facts, numbers, names, dates,
  recommendations, or conclusions NOT found in the original text.
- Paraphrasing or reorganizing information from the source is acceptable.
- Omitting information is acceptable (not a hallucination).
- Adding general knowledge, inferences, or plausible-sounding details NOT
  stated in the source IS a hallucination.

Respond with ONLY a JSON object (no markdown fences):
{"faithful": true, "hallucinations": []}
or
{"faithful": false, "hallucinations": ["first fabricated claim", "second fabricated claim"]}
```

**User message:**

```
ORIGINAL TEXT:
{source_text}

SUMMARY:
{summary}

Is every claim in the SUMMARY supported by the ORIGINAL TEXT? Return JSON.
```

## Full Evidence

All 15 prompts, raw model responses (including `<think>` reasoning), and GPT-5.2 judge verdicts are documented in **[summarization_evidence.md](summarization_evidence.md)**.

## Key Observations

1. **Chain-of-thought discipline**: The model's internal reasoning (`<think>` block) consistently includes self-reminders to "include only information from the text" and "not add external information" — this metacognitive behavior directly contributes to faithfulness.

2. **Structured output**: Summaries are organized with numbered sections, bold headers, and bullet points that map directly to the source document's article structure, making verification straightforward.

3. **No fabrication of specifics**: Critical details such as dates, monetary values, percentages, article numbers, and institutional names are reproduced exactly as they appear in the source text.

4. **Domain coverage**: The model handles technical vocabulary accurately across all three domains — legal terminology (licitações, calamidade pública), medical regulation (governança de IA, viés discriminatório), and financial instruments (LCD, FGC, CMN).

## Conclusion

The model **passes** the summarization faithfulness benchmark with a perfect score:

- **100% faithfulness rate** across all 15 texts and all 3 domains
- **Zero hallucinations** detected by the GPT-5.2 judge
- The model consistently reasons about avoiding external information and cross-checks its output against the source
- All summaries preserve factual accuracy for numbers, dates, article references, and domain-specific terminology

These results directly address Serpro's feedback regarding hallucinations in Legal and Medical domains. The model demonstrates it can summarize complex Brazilian government and institutional documents without inserting fabricated information, maintaining strict fidelity to the source text.
