# Portuguese Evaluation Benchmark

Portuguese (PT-BR) evaluation suite for the [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) framework, using **self-consistency sampling** (64 samples with majority voting).

## Methodology


| Parameter              | Value                                                 |
| ---------------------- | ----------------------------------------------------- |
| Sampling strategy      | Self-consistency (SC@64)                              |
| Samples per prompt     | 64 (`repeats: 64` in task YAML)                       |
| Decoding               | Stochastic (`do_sample: true`)                        |
| Temperature            | 0.7                                                   |
| Aggregation (discrete) | Majority vote over 64 regex-extracted labels          |
| Aggregation (STS)      | Median of 64 float predictions, clamped to [1.0, 5.0] |
| Few-shot               | 0-shot                                                |


**How it works:** Each prompt is sent to the model 64 times with `temperature=0.7`. For discrete-label tasks (MCQ, classification, NLI), the answer is extracted via regex from each response, and the most frequent answer is selected as the final prediction. For the STS task (continuous scores), the median of the 64 parsed float values is used.

This follows the same approach as [GSM8K self-consistency](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/tasks/gsm8k/gsm8k-cot-self-consistency.yaml) in the upstream lm-eval-harness.

## Tasks


| #   | Task                     | Category       | Dataset (HuggingFace)                           | Metric       | Aggregation   |
| --- | ------------------------ | -------------- | ----------------------------------------------- | ------------ | ------------- |
| 1   | `portuguese_enem`        | MCQ            | `eduagarcia/enem_challenge`                     | exact_match  | majority_vote |
| 2   | `portuguese_bluex`       | MCQ            | `eduagarcia-temp/BLUEX_without_images`          | exact_match  | majority_vote |
| 3   | `portuguese_oab_exams`   | MCQ            | `eduagarcia/oab_exams`                          | exact_match  | majority_vote |
| 4   | `portuguese_hatebr`      | Classification | `eduagarcia/portuguese_benchmark` (HateBR)      | f1_macro     | majority_vote |
| 5   | `portuguese_hate_speech` | Classification | `eduagarcia/portuguese_benchmark` (Hate Speech) | f1_macro     | majority_vote |
| 6   | `portuguese_tweetsentbr` | Classification | `eduagarcia/tweetsentbr_fewshot`                | f1_macro     | majority_vote |
| 7   | `portuguese_assin2_rte`  | NLI            | `assin2`                                        | f1_macro     | majority_vote |
| 8   | `portuguese_faquad_nli`  | NLI            | `ruanchaves/faquad-nli`                         | f1_macro     | majority_vote |
| 9   | `portuguese_assin2_sts`  | STS            | `assin2`                                        | pearson, mse | median        |


### Subgroups


| Group                       | Tasks                              |
| --------------------------- | ---------------------------------- |
| `portuguese_mcq`            | enem, bluex, oab_exams             |
| `portuguese_classification` | hatebr, hate_speech, tweetsentbr   |
| `portuguese_nli`            | assin2_rte, faquad_nli, assin2_sts |


## Setup

### 1. Clone lm-evaluation-harness

```bash
git clone https://github.com/EleutherAI/lm-evaluation-harness.git
cd lm-evaluation-harness
pip install -e .
```

### 2. Install additional dependencies

```bash
cd /path/to/this/directory
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

### Full benchmark (all 9 tasks)

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

### Save all 64 raw responses (for traceability)

```bash
python run_eval.py --save-all-samples
```

### CLI-level generation overrides

```bash
python run_eval.py --gen-kwargs "max_gen_toks=8192"
python run_eval.py --num-concurrent 50
```

### Run a single subgroup or task

```bash
python run_eval.py --tasks portuguese_mcq
python run_eval.py --tasks portuguese_enem
```

## Output

Results are saved to `output/results/{model_name}/{task_name}/`:

```
output/results/meetkai/functionary-pt-BR-v1.1/portuguese/
  results.json                          # aggregate scores per task
  samples_portuguese_enem_2026-03-31_120000.jsonl
  samples_portuguese_bluex_2026-03-31_120001.jsonl
  ...
```

### results.json

Aggregate metrics per task and group:

```json
{
  "results": {
    "portuguese_enem": {
      "exact_match,get_answer": 0.85,
      "exact_match_stderr,get_answer": 0.009
    }
  }
}
```

### samples JSONL (default: compact)

One JSON object per sample with the majority-vote prediction:

```json
{"doc_id": 0, "prompt": "...", "target": "C", "prediction": "C", "exact_match": 1.0}
```

### samples JSONL (with `--save-all-samples`)

Includes all 64 raw responses for full traceability:

```json
{"doc_id": 0, "prompt": "...", "target": "C", "prediction": "C", "exact_match": 1.0, "resps": [["C"], ["B"], ["C"], ...], "reasoning_content": [["..."], ...]}
```

## File Structure

```
.
├── README.md                    # this file
├── requirements.txt             # lm-eval + tomli
├── eval_config.toml             # model & task configuration
├── run_eval.py                  # evaluation runner
├── f1_utils.py                  # shared filters (regex_last, median_float_vote)
└── portuguese/                  # lm-eval task YAMLs
    ├── portuguese.yaml          # top-level group
    ├── classification/
    │   ├── _default_classification_yaml
    │   ├── portuguese_classification.yaml
    │   ├── portuguese_hatebr.yaml
    │   ├── portuguese_hate_speech.yaml
    │   ├── portuguese_tweetsentbr.yaml
    │   └── utils.py
    ├── mcq/
    │   ├── _default_mcq_yaml
    │   ├── portuguese_mcq.yaml
    │   ├── portuguese_enem.yaml
    │   ├── portuguese_bluex.yaml
    │   ├── portuguese_oab_exams.yaml
    │   └── utils.py
    └── nli/
        ├── portuguese_nli.yaml
        ├── portuguese_assin2_rte.yaml
        ├── portuguese_faquad_nli.yaml
        ├── portuguese_assin2_sts.yaml
        └── utils.py
```

## Dataset Sources


| Dataset     | HuggingFace Path                       | Config                          | Split | Fields                                                      |
| ----------- | -------------------------------------- | ------------------------------- | ----- | ----------------------------------------------------------- |
| ENEM        | `eduagarcia/enem_challenge`            | --                              | train | question, choices, answerKey                                |
| BLUEX       | `eduagarcia-temp/BLUEX_without_images` | --                              | train | question, choices, answerKey                                |
| OAB Exams   | `eduagarcia/oab_exams`                 | --                              | train | question, choices, answerKey                                |
| HateBR      | `eduagarcia/portuguese_benchmark`      | `HateBR_offensive_binary`       | test  | sentence, label                                             |
| Hate Speech | `eduagarcia/portuguese_benchmark`      | `Portuguese_Hate_Speech_binary` | test  | sentence, label                                             |
| TweetSentBR | `eduagarcia/tweetsentbr_fewshot`       | --                              | test  | sentence, label                                             |
| ASSIN2      | `assin2`                               | --                              | test  | premise, hypothesis, entailment_judgment, relatedness_score |
| FaQuAD-NLI  | `ruanchaves/faquad-nli`                | --                              | test  | question, answer, label                                     |


