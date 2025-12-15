# Tagging Bills with Semantic Similarity

The `govbot tag` command can automatically tag legislative logs using semantic similarity matching.

## Quick Start

1. **Place required files in your working directory:**

   - `tags.toml` - Tag definitions (see example below)
   - `model.onnx` - ONNX sentence transformer model (e.g., all-MiniLM-L6-v2)
   - `tokenizer.json` - Tokenizer file for the model

2. **Run the command:**
   ```bash
   just govbot logs --repos il --limit 10 | just govbot tag
   ```

The command will automatically detect `tags.toml` and use embedding mode if all three files are present.

## Tag Configuration (tags.toml)

Each tag defines:

- `name`: The tag identifier
- `description`: Semantic description of what the tag represents
- `threshold`: Minimum similarity score (0.0-1.0) to match
- `examples`: Optional example phrases (helps improve matching)

Example:

```toml
[[tag]]
name = "education"
description = "Legislation related to schools, education funding, curriculum standards, teacher certification, higher education policy, student loans, charter schools"
threshold = 0.60
examples = [
    "School funding bill",
    "Teacher certification requirements"
]
```

## Getting the Model Files

To use embedding mode, you need:

1. **ONNX Model**: Convert a sentence transformer model to ONNX

   ```bash
   # Using optimum-cli (requires Python)
   pip install optimum[onnxruntime]
   optimum-cli export onnx --model sentence-transformers/all-MiniLM-L6-v2 minilm-l6-v2-onnx/
   ```

2. **Tokenizer**: The tokenizer.json file is included in the exported model directory

3. **Copy files**: Place `model.onnx` and `tokenizer.json` in your working directory

## Alternative: Using Built-in TF-IDF Mode

If you don't have model files, you can use the built-in TF-IDF similarity matcher:

```bash
just govbot logs --repos il --limit 10 | \
  just govbot tag --ai-tool builtin --tags "education,budget,healthcare"
```

## Output

Tagged results are written to:

```
country:us/state:{locale}/sessions/{session_id}/tags.json
```

The output format:

```json
{
  "bills": {
    "SB1234": [
      ["education", 0.85],
      ["budget", 0.72]
    ]
  },
  "tags": {
    "education": "Legislation related to schools...",
    "budget": "Legislation concerning state budgets..."
  }
}
```
