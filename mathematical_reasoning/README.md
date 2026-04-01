# Mathematical Reasoning Benchmark (GSM8K + MATH-500)

Mathematical reasoning evaluation using two standard benchmarks — [GSM8K](https://huggingface.co/datasets/openai/gsm8k) and [MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500) — via the [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) framework, with greedy decoding (single deterministic pass).

## Methodology

| Parameter         | Value                                                              |
| ----------------- | ------------------------------------------------------------------ |
| Sampling strategy | Greedy (single pass)                                               |
| Samples per prompt| 1 (`repeats: 1` in task YAML)                                      |
| Decoding          | Deterministic (`do_sample: false`)                                 |
| Temperature       | 0                                                                  |
| Max tokens        | 8192 (`max_gen_toks: 8192`)                                        |
| Few-shot          | 0-shot                                                             |
| Metric (GSM8K)    | `exact_match` (accuracy on extracted numerical answer)             |
| Metric (MATH-500) | `exact_match` (normalized LaTeX + SymPy equivalence) and `math_verify` (symbolic verification) |

**How it works:** Each problem is sent to the model once with `temperature=0` (greedy decoding). The model is instructed to reason step by step and produce a structured final answer. The answer is then extracted and compared against the gold-standard label.

- **GSM8K:** The numerical answer is extracted via regex (looking for `#### N` format or falling back to the last number in the response). Accuracy is the fraction of correctly answered questions.
- **MATH-500:** The LaTeX answer is extracted from `\boxed{...}`, normalized (Lewkowycz et al., 2022 Appendix D), and compared both via string matching and symbolic equivalence (SymPy). The `math_verify` metric provides an additional symbolic verification layer.

For models that produce `<think>…</think>` reasoning wrappers, the `strip_think_recover` filter removes the wrapper before answer extraction, falling back to the last non-empty line of the reasoning block if the content field is empty.

## Tasks

| Task             | Dataset (HuggingFace)       | Split | Samples | Answer Format       | Metric(s)                     |
| ---------------- | --------------------------- | ----- | ------- | ------------------- | ----------------------------- |
| `gsm8k_zeroshot` | `openai/gsm8k` (main)      | test  | 1,319   | Numerical (`#### N`)| `exact_match`                 |
| `math500`        | `HuggingFaceH4/MATH-500`   | test  | 500     | LaTeX (`\boxed{}`)  | `exact_match`, `math_verify`  |

### GSM8K

Grade School Math 8K contains 8,500 linguistically diverse grade-school-level math word problems (1,319 in the test split). Each problem requires 2–8 steps of basic arithmetic and reasoning to solve. Answers are always integers.

**Dataset fields:**

| Field      | Description                                          |
| ---------- | ---------------------------------------------------- |
| `question` | The math word problem                                |
| `answer`   | Step-by-step solution ending with `#### N` (integer) |

### MATH-500

A curated 500-problem subset of the [MATH benchmark](https://github.com/hendrycks/math) (Hendrycks et al., 2021), spanning 7 mathematical topics: algebra, counting & probability, geometry, intermediate algebra, number theory, prealgebra, and precalculus. Answers are LaTeX expressions enclosed in `\boxed{}`.

**Dataset fields:**

| Field      | Description                                           |
| ---------- | ----------------------------------------------------- |
| `problem`  | The mathematical problem statement                    |
| `solution` | Full solution with final answer in `\boxed{}`         |

## Prompt Format

### GSM8K

```
Solve the following math problem step by step. After your reasoning, provide the final numerical answer on a new line prefixed with "#### ".

Question:
{question}

Answer:
```

### MATH-500

```
Solve the following math problem step by step. Present your final answer enclosed in \boxed{}.

Problem:
{problem}

Solution:
```

## Answer Extraction

### GSM8K (filter-based)

Two filter pipelines run in parallel:

1. **strict-match:** `strip_think_recover` → regex `#### (\-?[0-9\.\,]+)` → `take_first`
2. **flexible-extract:** `strip_think_recover` → `regex_last` (last number in response) → `take_first`

The `exact_match` metric compares the extracted number against the gold answer, ignoring commas and dollar signs.

### MATH-500 (process_results)

Uses `process_results` (custom Python function) instead of filter-based extraction:

1. Strip `<think>` tags from model output
2. Extract `\boxed{...}` content (or fall back to "Final Answer: ..." format)
3. Normalize LaTeX (Lewkowycz et al., 2022 Appendix D)
4. Compare via `is_equiv()` — SymPy symbolic comparison (`exact_match` metric)
5. Compare via `math_verify` package — independent symbolic verification (`math_verify` metric)

## Setup

### 1. Clone lm-evaluation-harness

```bash
git clone https://github.com/EleutherAI/lm-evaluation-harness.git
cd lm-evaluation-harness
pip install -e .
```

### 2. Install additional dependencies

```bash
cd /path/to/mathematical_reasoning
pip install -r requirements.txt
```

The `requirements.txt` installs:
- `lm-eval>=0.4.0` — evaluation harness
- `sympy` — symbolic math for LaTeX equivalence checking
- `math-verify` — additional symbolic verification
- `antlr4-python3-runtime==4.11.1` — required by SymPy's LaTeX parser

### 3. Set your API key

```bash
export OPENAI_API_KEY="your-key"
```

### 4. Configure your model

Edit `eval_config.toml`:

```toml
[[models]]
name = "your-model-name"          # display name (used in output dirs)
model_id = "provider/model-id"    # model ID sent to the API

[defaults]
base_url = "https://your-endpoint/v1/chat/completions"
```

## Running

### Full benchmark (both tasks)

```bash
python run_eval.py
```

### Individual tasks

```bash
python run_eval.py --tasks gsm8k_zeroshot
python run_eval.py --tasks math500
```

### Specific model

```bash
python run_eval.py --models your-model-name
```

### Dry run (print parameters only)

```bash
python run_eval.py --dry-run
```

### CLI-level generation overrides

```bash
python run_eval.py --gen-kwargs "max_gen_toks=16384"
python run_eval.py --num-concurrent 50
```

### Limit to first N samples (for testing)

```bash
python run_eval.py --limit 20
```

## Output

Results are saved to `output/results/{model_name}/{task_name}/`:

```
output/results/your-model/gsm8k_zeroshot/
  results.json
  samples_gsm8k_zeroshot_2026-04-01_120000.jsonl

output/results/your-model/math500/
  results.json
  samples_math500_2026-04-01_120000.jsonl
```

### results.json

Aggregate metrics produced by lm-evaluation-harness:

```json
{
  "results": {
    "gsm8k_zeroshot": {
      "exact_match,strict-match": 0.75,
      "exact_match_stderr,strict-match": 0.012,
      "exact_match,flexible-extract": 0.77,
      "exact_match_stderr,flexible-extract": 0.011
    }
  },
  "groups": {
    "mathematical_reasoning": {
      "exact_match,strict-match": 0.75,
      "exact_match_stderr,strict-match": 0.012
    }
  }
}
```

For MATH-500:

```json
{
  "results": {
    "math500": {
      "exact_match": 0.45,
      "exact_match_stderr": 0.022,
      "math_verify": 0.48,
      "math_verify_stderr": 0.022
    }
  }
}
```

The key metrics are:
- **GSM8K:** `exact_match,strict-match` and `exact_match,flexible-extract` — accuracy (fraction of correctly solved problems)
- **MATH-500:** `exact_match` — accuracy via normalized string + SymPy comparison; `math_verify` — accuracy via symbolic verification

### samples JSONL

One JSON object per sample:

```json
{"doc_id": 0, "prompt": "Solve the following math problem...", "target": "42", "prediction": "42", "exact_match": 1.0}
```

## File Structure

```
mathematical_reasoning/
├── README.md                       # this file
├── requirements.txt                # lm-eval + math dependencies
├── eval_config.toml                # model & task configuration
├── run_eval.py                     # evaluation runner (lm_eval.simple_evaluate)
├── f1_utils.py                     # shared filters (strip_think_recover, regex_last)
├── mathematical_reasoning.yaml     # task group definition
├── gsm8k_zeroshot.yaml             # GSM8K task definition (0-shot, greedy)
├── gsm8k_utils.py                  # GSM8K prompt formatting & answer extraction
├── math500.yaml                    # MATH-500 task definition (0-shot, greedy)
└── math500_utils.py                # MATH-500 prompt formatting, boxed-answer extraction, symbolic equivalence
```

## References

- **GSM8K Paper:** Cobbe, K., et al. (2021). *Training Verifiers to Solve Math Word Problems.* [arXiv:2110.14168](https://arxiv.org/abs/2110.14168)
- **MATH Paper:** Hendrycks, D., et al. (2021). *Measuring Mathematical Problem Solving With the MATH Dataset.* NeurIPS 2021. [arXiv:2103.03874](https://arxiv.org/abs/2103.03874)
- **MATH-500 Subset:** [HuggingFaceH4/MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500)
- **Minerva Normalization:** Lewkowycz, A., et al. (2022). *Solving Quantitative Reasoning Problems with Language Models.* NeurIPS 2022. [arXiv:2206.14858](https://arxiv.org/abs/2206.14858)
- **lm-evaluation-harness:** [github.com/EleutherAI/lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)
- **HuggingFace GSM8K:** [openai/gsm8k](https://huggingface.co/datasets/openai/gsm8k)
