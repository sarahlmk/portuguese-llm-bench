# Summarization Faithfulness Benchmark

Evaluates whether a language model can produce faithful summaries of domain-specific Brazilian Portuguese texts **without inserting hallucinated information**.

Directly addresses Serpro's feedback on hallucinations in generated summaries (e.g., inserting "execução contínua" in Legal contracts, fabricating monitoring recommendations in Medical reports).

## Methodology

1. **Source texts**: 15 real, publicly available Brazilian government and institutional documents across 3 domains (5 each):
   - **Jurídico (Legal)**: Decreto 12.198/2024 (Governo Digital), Decreto 12.304/2024 (Programas de Integridade), Lei 13.709/2018 — LGPD (2 sections), Lei Complementar 206/2024 (Calamidade Pública)
   - **Médico (Medical)**: Resolução CFM 2454/2026 — IA na Medicina (3 sections), Decreto 11.908/2024 (Brasil Saudável), Decreto 11.999/2024 (Residência)
   - **Financeiro (Financial)**: Lei 14.937/2024 (LCD), CVM Ofício Circular Anual 2024/SEP (3 sections), Lei Complementar 179/2021 (Autonomia do BCB)

   All source texts are extracted verbatim from official publications (planalto.gov.br, legisweb.com.br, conteudo.cvm.gov.br) — no fictional content.

2. **Summarization**: The model receives a bare user message (no system prompt) asking it to summarize the source text concisely and accurately.

3. **LLM-as-judge (gpt-5.2)**: A judge model evaluates each summary for faithfulness — does the summary contain ONLY information from the source? If the model fabricates facts, numbers, recommendations, or conclusions not in the original text, it is flagged as a hallucination.

## Metrics

| Metric | Description | Ideal |
|---|---|---|
| **Faithfulness Rate** | % of summaries with zero hallucinations | 100% |
| **Per-domain breakdown** | Faithfulness per domain (Jurídico, Médico, Financeiro) | — |

## Usage

```bash
# Quick test (3 texts)
python run_summarization.py --base-url https://functionary-inference-pt-br.meetkai.ai/v1 \
    --model meetkai/functionary-pt-BR-v1.1 --limit 3

# Full benchmark with LLM judge
python run_summarization.py --base-url https://functionary-inference-pt-br.meetkai.ai/v1 \
    --model meetkai/functionary-pt-BR-v1.1 \
    --judge-base-url https://api.openai.com/v1 \
    --judge-api-key $OPENAI_API_KEY

# Using OpenRouter for both generation and judging
python run_summarization.py --base-url https://openrouter.ai/api/v1 \
    --model meetkai/functionary-pt-BR-v1.1 \
    --judge-model openai/gpt-5.2

# Higher concurrency
python run_summarization.py --base-url https://functionary-inference-pt-br.meetkai.ai/v1 \
    --model meetkai/functionary-pt-BR-v1.1 --num-concurrent 4
```

## CLI Arguments

### Generation (target model)

| Flag | Default | Description |
|---|---|---|
| `--base-url` | *(required)* | OpenAI-compatible API base URL |
| `--model` | *(required)* | Model ID sent to the API |
| `--api-key` | `$OPENAI_API_KEY` | Model API key |
| `--temperature` | `0.3` | Sampling temperature |
| `--max-tokens` | `1024` | Max tokens per summary |
| `--limit` | all | Only evaluate first N texts |
| `--num-concurrent` | `1` | Parallel requests |

### Judge (faithfulness evaluator)

| Flag | Default | Description |
|---|---|---|
| `--judge-model` | `gpt-5.2` | Judge model ID |
| `--judge-base-url` | `https://api.openai.com/v1` | Judge API base URL |
| `--judge-api-key` | `$OPENAI_API_KEY` | Judge API key |

### Output

| Flag | Default | Description |
|---|---|---|
| `--output-dir` | `output/summarization` | Output directory |
| `--source-texts` | bundled `source_texts.json` | Path to custom source texts |

## Output Files

- `results.json` — Aggregate metrics (faithfulness rate, per-domain breakdown)
- `samples.jsonl` — Per-item details (source text, summary, judge verdict, hallucinations found)

## Dependencies

```bash
pip install -r requirements.txt
```
