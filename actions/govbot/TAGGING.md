# Tagging Bills with Semantic Similarity

The `govbot tag` command can automatically tag legislative logs using semantic similarity matching.

### How tagging works

- **Primary mode (embeddings)**: Uses a sentence-transformer model (`model.onnx` + `tokenizer.json`) to embed logs and tags, combining:
  - **Base similarity** between the log text and each tag’s description/examples
  - **Example similarity** to individual positive examples
  - **Keyword boosts** from `include_keywords` / `exclude_keywords`
  - **Negative examples** penalties via `negative_examples`
- **Fallback mode (keywords only)**: If the embedding model or tokenizer cannot be loaded, govbot falls back to **keyword-based tagging** using `include_keywords` / `exclude_keywords` from the tag definitions.

In both modes, each tag has a **`threshold`** and a structured **score breakdown** is stored in per-tag `.tag.json` files.

## Quick Start

1. **Place required files in your working directory:**

   - `govbot.yml` – Tag definitions (see below)
   - `model.onnx` – ONNX sentence transformer model (e.g., all-MiniLM-L6-v2)
   - `tokenizer.json` – Tokenizer file for the model

2. **Run the command:**

   ```bash
   just govbot logs --repos il --limit 10 | just govbot tag
   ```

govbot will:

- Require `govbot.yml`
- Try to use **embedding mode** (`model.onnx` + `tokenizer.json`)
- If embeddings are unavailable or fail to initialize, automatically **fall back to keyword-based matching** (using `include_keywords` / `exclude_keywords`).

## Tag Configuration (`govbot.yml`)

Each tag defines (YAML schema):

- `name`: Tag identifier (key name in `tags:` map)
- `description`: Semantic description of what the tag represents
- `threshold`: Minimum similarity score (0.0–1.0) to match
- `examples`: Optional positive example phrases (improves embeddings)
- `include_keywords`: Phrases whose presence should strongly favor this tag
- `exclude_keywords`: Phrases that should block this tag
- `negative_examples`: Texts that should **not** match this tag (used as embedding negatives)

Example:

```yaml
tags:
  education:
    description: >
      Legislation related to schools, education funding, curriculum standards,
      teacher certification, higher education policy, student loans, charter schools
    threshold: 0.6
    examples:
      - School funding bill
      - Teacher certification requirements
    include_keywords:
      - education
      - school funding
      - curriculum
    exclude_keywords:
      - driver education
    negative_examples:
      - Resolution honoring local high school sports teams
```

## Getting the Model Files

To use embedding mode, you need:

1. **ONNX Model**: Convert a sentence transformer model to ONNX

   ```bash
   # Using optimum-cli (requires Python)
   pip install optimum[onnxruntime]
   optimum-cli export onnx --model sentence-transformers/all-MiniLM-L6-v2 minilm-l6-v2-onnx/
   ```

2. **Tokenizer**: The `tokenizer.json` file is included in the exported model directory.

3. **Copy files**: Place `model.onnx` and `tokenizer.json` in your working directory (or in the directory pointed to by `--govbot-dir` / `GOVBOT_DIR`).

If either file is missing or cannot be loaded, govbot will **still run** using the keyword-based fallback described above.

## Output

Tagged results are written to per-tag files under the session’s `tags/` directory:

```text
country:us/state:{state}/sessions/{session_id}/tags/{tag_name}.tag.json
```

Each `{tag_name}.tag.json` file contains:

- `metadata`: Model info, last run timestamp, hash of the tag config
- `tag_config`: The tag definition as used on the last run
- `text_cache`: Deduplicated bill/log texts keyed by content hash
- `bills`: Map of bill identifiers to their `ScoreBreakdown`

`ScoreBreakdown` includes:

- `final_score`: Final score used for threshold comparison
- `base_embedding`: Base embedding similarity (if embeddings were used)
- `example_similarity`: Max similarity to positive examples
- `keyword_match`: Whether include_keywords matched
- `negative_penalty`: Penalty applied from negative examples (if any)
