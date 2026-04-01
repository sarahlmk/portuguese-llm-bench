# portuguese-llm-bench

Unified evaluation suite for Portuguese LLMs -- covering language understanding, reasoning, safety, toxicity, and bias benchmarks.

## Benchmarks

| # | Benchmark | Directory | Tasks | Methodology | Key Metrics |
|---|-----------|-----------|-------|-------------|-------------|
| 1 | **Language Understanding** | [`language_understanding/`](language_understanding/) | ENEM, BLUEX, OAB (MCQ); HateBR, Hate Speech, TweetSentBR (classification); ASSIN2 RTE, FaQuAD-NLI (NLI); ASSIN2 STS | Self-consistency sampling (SC@64, majority vote) via lm-eval-harness | exact_match, f1_macro, pearson |
| 2 | **Logical Reasoning** | [`logical_reasoning/`](logical_reasoning/) | LogiQA (651 questions, 4-choice) | Greedy decoding (single pass) via lm-eval-harness | exact_match (accuracy) |
| 3 | **Mathematical Reasoning** | [`mathematical_reasoning/`](mathematical_reasoning/) | GSM8K (1,319 problems), MATH-500 (500 problems) | Greedy decoding (single pass) via lm-eval-harness | exact_match, math_verify |
| 4 | **Toxicity** | [`toxicity/`](toxicity/) | RealToxicityPrompts (100K prompts, 25 continuations each) | Nucleus sampling + ML toxicity scorer (Detoxify / OpenAI Moderation / Perspective API) | Expected Max Toxicity, Toxicity Probability |
| 5 | **Safety Refusals** | [`safety_refusals/`](safety_refusals/) | Do-Not-Answer (939 harmful prompts, 5 risk areas) | LLM-as-judge classification (6 action categories) | Correct Refusal Rate, Harmful Response Rate |
| 6 | **Sociocultural Bias** | [`sociocultural_bias/`](sociocultural_bias/) | StereoSet (intrasentence, ~2K items, 4 bias categories) | MCQ prompting with randomized options + before/after comparison | LMS, SS, ICAT |

## Results — functionary-pt-BR-v1.1

| Benchmark | Task | Metric | Score |
|-----------|------|--------|------:|
| Logical Reasoning | LogiQA | exact_match | 0.7189 |
| Mathematical Reasoning | GSM8K (flexible) | exact_match | 0.9045 |
| Mathematical Reasoning | GSM8K (strict) | exact_match | 0.8961 |
| Safety Refusals | Do-Not-Answer | correct_refusal_rate | 93.08% |
| Toxicity | RealToxicityPrompts* | expected_max_toxicity | 0.0171 |
| Toxicity | RealToxicityPrompts* | toxicity_probability | 0.0000 |

\* Preliminary run (10 prompts, 5 samples). Full benchmark pending.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/portuguese-llm-bench.git
cd portuguese-llm-bench
```

### 2. Install dependencies

Install all dependencies at once:

```bash
pip install -r requirements.txt
```

Or install only what a specific benchmark needs:

```bash
pip install -r language_understanding/requirements.txt
pip install -r logical_reasoning/requirements.txt
pip install -r mathematical_reasoning/requirements.txt
pip install -r toxicity/requirements.txt
pip install -r safety_refusals/requirements.txt
pip install -r sociocultural_bias/requirements.txt
```

Benchmarks that use [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) also require it to be installed:

```bash
git clone https://github.com/EleutherAI/lm-evaluation-harness.git
cd lm-evaluation-harness
pip install -e .
```

### 3. Set your API key

```bash
export OPENAI_API_KEY="your-key"
```

### 4. Run a benchmark

Each benchmark has its own runner script. See the README inside each directory for full usage.

```bash
# Language Understanding (9 PT-BR tasks, self-consistency sampling)
cd language_understanding
python run_eval.py

# Logical Reasoning (LogiQA, greedy)
cd logical_reasoning
python run_eval.py

# Mathematical Reasoning (GSM8K + MATH-500, greedy)
cd mathematical_reasoning
python run_eval.py

# Toxicity (RealToxicityPrompts)
cd toxicity
python run_toxicity.py --base-url https://your-endpoint/v1 --model your-model-id

# Safety Refusals (Do-Not-Answer)
cd safety_refusals
python run_refusals.py --base-url https://your-endpoint/v1 --model your-model-id

# Sociocultural Bias (StereoSet)
cd sociocultural_bias
python run_stereoset.py --base-url https://your-endpoint/v1 --model your-model-id
```

## Repository Structure

```
portuguese-llm-bench/
├── README.md                       # this file
├── requirements.txt                # all dependencies (union of per-benchmark deps)
├── LICENSE                         # Apache 2.0
│
├── language_understanding/         # PT-BR MCQ, classification, NLI, STS (lm-eval-harness)
│   ├── README.md
│   ├── run_eval.py
│   ├── eval_config.toml
│   └── portuguese/                 # lm-eval task YAMLs
│
├── logical_reasoning/              # LogiQA (lm-eval-harness)
│   ├── README.md
│   ├── run_eval.py
│   ├── eval_config.toml
│   └── logiqa.yaml
│
├── mathematical_reasoning/         # GSM8K + MATH-500 (lm-eval-harness)
│   ├── README.md
│   ├── run_eval.py
│   ├── eval_config.toml
│   ├── gsm8k_zeroshot.yaml
│   └── math500.yaml
│
├── toxicity/                       # RealToxicityPrompts
│   ├── README.md
│   └── run_toxicity.py
│
├── safety_refusals/                # Do-Not-Answer
│   ├── README.md
│   └── run_refusals.py
│
└── sociocultural_bias/             # StereoSet (bias)
    ├── README.md
    ├── run_stereoset.py
    └── compare_stereoset.py
```

## Datasets

| Dataset | Source | Benchmark |
|---------|--------|-----------|
| ENEM Challenge | [eduagarcia/enem_challenge](https://huggingface.co/datasets/eduagarcia/enem_challenge) | Language Understanding |
| BLUEX | [eduagarcia-temp/BLUEX_without_images](https://huggingface.co/datasets/eduagarcia-temp/BLUEX_without_images) | Language Understanding |
| OAB Exams | [eduagarcia/oab_exams](https://huggingface.co/datasets/eduagarcia/oab_exams) | Language Understanding |
| HateBR | [eduagarcia/portuguese_benchmark](https://huggingface.co/datasets/eduagarcia/portuguese_benchmark) | Language Understanding |
| Hate Speech | [eduagarcia/portuguese_benchmark](https://huggingface.co/datasets/eduagarcia/portuguese_benchmark) | Language Understanding |
| TweetSentBR | [eduagarcia/tweetsentbr_fewshot](https://huggingface.co/datasets/eduagarcia/tweetsentbr_fewshot) | Language Understanding |
| ASSIN2 | [assin2](https://huggingface.co/datasets/assin2) | Language Understanding |
| FaQuAD-NLI | [ruanchaves/faquad-nli](https://huggingface.co/datasets/ruanchaves/faquad-nli) | Language Understanding |
| LogiQA | [EleutherAI/logiqa](https://huggingface.co/datasets/EleutherAI/logiqa) | Logical Reasoning |
| GSM8K | [openai/gsm8k](https://huggingface.co/datasets/openai/gsm8k) | Mathematical Reasoning |
| MATH-500 | [HuggingFaceH4/MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500) | Mathematical Reasoning |
| RealToxicityPrompts | [allenai/real-toxicity-prompts](https://huggingface.co/datasets/allenai/real-toxicity-prompts) | Toxicity |
| Do-Not-Answer | [LibrAI/do-not-answer](https://huggingface.co/datasets/LibrAI/do-not-answer) | Safety Refusals |
| StereoSet | [McGill-NLP/stereoset](https://huggingface.co/datasets/McGill-NLP/stereoset) | Sociocultural Bias |

## License

Apache 2.0 -- see [LICENSE](LICENSE).
