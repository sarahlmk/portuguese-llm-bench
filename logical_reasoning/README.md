# Logical Reasoning Benchmark (LogiQA)

Logical reasoning evaluation using the [LogiQA](https://huggingface.co/datasets/EleutherAI/logiqa) dataset via the [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) framework, with greedy decoding (single deterministic pass).

## Methodology

| Parameter         | Value                                              |
| ----------------- | -------------------------------------------------- |
| Sampling strategy | Greedy (single pass)                               |
| Samples per prompt| 1 (`repeats: 1` in task YAML)                      |
| Decoding          | Deterministic (`do_sample: false`)                 |
| Temperature       | 0                                                  |
| Max tokens        | 8192 (`max_gen_toks: 8192`)                        |
| Aggregation       | First regex-extracted letter (A/B/C/D)             |
| Few-shot          | 0-shot                                             |
| Metric            | `exact_match` (accuracy)                           |

**How it works:** Each prompt is sent to the model once with `temperature=0` (greedy decoding). The answer letter (A, B, C, or D) is extracted from the response via regex, and compared against the gold-standard label. Accuracy is the fraction of correctly answered questions across all test samples.

For models that produce `<think>…</think>` reasoning wrappers, the `strip_think_recover` filter removes the wrapper before regex extraction, falling back to the last non-empty line of the reasoning block if the content field is empty.

## Task

| Task     | Dataset (HuggingFace)  | Split | Samples | Choices | Metric      |
| -------- | ---------------------- | ----- | ------- | ------- | ----------- |
| `logiqa` | `EleutherAI/logiqa`    | test  | 651     | 4 (A–D) | exact_match |

### Dataset Fields

| Field     | Description                           |
| --------- | ------------------------------------- |
| `context` | Background passage for reasoning      |
| `question`| The logical reasoning question        |
| `options` | List of 4 answer choices              |
| `label`   | Correct answer (`a`, `b`, `c`, or `d`)|

### Prompt Format

```
Read the following passage and answer the question by selecting the correct option. Reply with only the letter (A, B, C, or D).

Passage:
{context}

Question:
{question}

Choices:
A. {option_0}
B. {option_1}
C. {option_2}
D. {option_3}

Answer:
```

## Results

| Model | Task | Metric | Score | Stderr |
|-------|------|--------|------:|-------:|
| functionary-pt-BR-v1.1 | LogiQA | exact_match | 0.7189 | ±0.0176 |

## Setup

### 1. Clone lm-evaluation-harness

```bash
git clone https://github.com/EleutherAI/lm-evaluation-harness.git
cd lm-evaluation-harness
pip install -e .
```

### 2. Install additional dependencies

```bash
cd /path/to/logical_reasoning
pip install -r requirements.txt
```

### 3. Set your API key

```bash
export OPENAI_API_KEY="your-key"
```

### 4. Configure your model

Edit `eval_config.toml`:

```toml
[[models]]
name = "meetkai/functionary-pt-BR-v1.1"          # display name (used in output dirs)
model_id = "provider/model-id"    # model ID sent to the API

[defaults]
base_url = "https://functionary-inference-pt-br.meetkai.ai/v1/chat/completions"
```

## Running

### Full benchmark

```bash
python run_eval.py
```

### Specific model

```bash
python run_eval.py --models meetkai/functionary-pt-BR-v1.1
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

Results are saved to `output/results/{model_name}/logical_reasoning/`:

```
output/results/meetkai/functionary-pt-BR-v1.1/logical_reasoning/
  results.json
  samples_logiqa_2026-04-01_120000.jsonl
```

### results.json

Aggregate metrics:

```json
{
  "results": {
    "logiqa": {
      "exact_match,get_answer": 0.42,
      "exact_match_stderr,get_answer": 0.019
    }
  },
  "groups": {
    "logical_reasoning": {
      "exact_match,get_answer": 0.42,
      "exact_match_stderr,get_answer": 0.019
    }
  }
}
```

The key metric is `exact_match,get_answer` — this is the **accuracy** (fraction of correctly answered questions).

### samples JSONL

One JSON object per sample:

```json
{"doc_id": 0, "prompt": "Read the following passage...", "target": "A", "prediction": "A", "exact_match": 1.0}
```

## File Structure

```
logical_reasoning/
├── README.md                   # this file
├── requirements.txt            # lm-eval + tomli
├── eval_config.toml            # model & task configuration
├── run_eval.py                 # evaluation runner (lm_eval.simple_evaluate)
├── f1_utils.py                 # shared filters (strip_think_recover, regex)
├── logical_reasoning.yaml      # task group definition
├── logiqa.yaml                 # LogiQA task definition
└── utils.py                    # prompt formatting (doc_to_text, doc_to_target)
```

## References

- **LogiQA Paper:** Liu, J., et al. (2020). *LogiQA: A Challenge Dataset for Machine Reading Comprehension with Logical Reasoning.* IJCAI 2020. [arXiv:2007.08124](https://arxiv.org/abs/2007.08124)
- **HuggingFace Dataset:** [EleutherAI/logiqa](https://huggingface.co/datasets/EleutherAI/logiqa)
- **lm-evaluation-harness:** [github.com/EleutherAI/lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)
