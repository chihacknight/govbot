# govbot stack — frozen cross-domain contract

**Status:** FROZEN for the layering refactor (build-sequence steps 1–6).
**Owner:** head architect. Subagents treat this as read-only input. A subagent that
finds the contract unworkable must escalate to the architect for a re-freeze — it does
not change the contract unilaterally.

This is the load-bearing interface between the three layers — `fastclass` (classifier),
`govbot` (gov-data tool), and userland apps. The layers compose over **process
boundaries** (newline-delimited JSON on stdio), never as linked libraries.

---

## 1. The input stream protocol (govbot → transform)

`govbot` streams documents to a transform (e.g. `fastclass classify -`) as
**newline-delimited JSON** — one object per line, UTF-8, `\n`-terminated:

```json
{"id": "<opaque string>", "text": "<string>", "kind": "docs"}
```

- **`id`** — an opaque routing key. The transform treats it as opaque and **echoes it
  back unchanged** in the result. For govbot's `docs` projection it is the bill's
  dataset path; no consumer parses its structure.
- **`text`** — the document body. For govbot's `docs` projection this is the **full
  bill text** assembled from `metadata.json` (not just titles).
- **`kind`** — **required**. Tags the stream record type (`docs` today; future
  `summary`, etc.). A transform that does not recognize a `kind` **passes the record
  through untouched** rather than erroring.

A transform reads this stream line-by-line and emits one result line per input line.

## 2. The classify result (`ClassifyResult`)

`fastclass classify` emits one `ClassifyResult` JSON object per input document. The
echoed identifier field is named **`doc`** (NOT `id`) — this is frozen; downstream
sinks (`govbot apply`) route on `doc`. Full shape — see
`fastclass/schemas/result.schema.json` for the machine-readable schema:

```json
{
  "doc": "<echoed id, unchanged>",
  "text_hash": "sha256:<hex>",
  "classifier_version": "sha256:<12-hex>",
  "fusion_version": "fusion-v1",
  "tags": {
    "<tag name>": {
      "matched": true,
      "threshold": 0.3,
      "matcher_outputs": [
        {"kind": "keyword", "version": "...", "role": "scorer",
         "raw_score": 1.0, "evidence": [{"kind": "keyword_hit", "detail": "solar"}]}
      ],
      "fusion": {"version": "fusion-v1", "final_score": 0.92, "gated": false}
    }
  }
}
```

- `matcher_outputs[].role` is one of `scorer` | `gate` | `penalty`.
- `tags` is ordered by tag name (byte-stable, snapshot-testable).

## 3. `fastclass describe`

`fastclass describe classifier=<bundle>` emits a single JSON object so govbot can
type-check a transform DAG and validate that `publish.*.select:` tag names exist:

```json
{
  "reads": ["docs"],
  "writes": ["classification"],
  "tags": ["clean_energy", "conservation", "emissions_and_climate", "fossil_fuels"],
  "classifier_version": "sha256:<12-hex>",
  "fusion_version": "fusion-v1"
}
```

- `tags` is the sorted list of active tag names from the bundle.
- `describe` is a **subcommand** (not a `classify` flag).

## 4. The classifier-bundle layout

A classifier bundle is a **directory**. `fastclass` owns its contents; `govbot` only
passes the path (`classifier=<bundle>`). `fastclass` must NOT know the word "govbot" —
`govbot.yml` is **not** a recognized bundle file.

```
<bundle>/
  classifier.yml        taxonomy (REQUIRED; `fastclass.yml` is an accepted alias)
  fusion.yml            fusion weights + the cascade "uncertainty band" (optional)
  eval/
    constitution.yml    frozen gold set — never enters an LLM context
    rolling.yml         refreshable working eval set (optional)
  proposals/            improvement-proposal history
  model/                optional embedding model
  fastclass.lock        pins bundle + binary versions for lineage
```

## 5. Calibrated scores

`fusion.final_score` is contractually a **calibrated** probability in `[0, 1]` —
downstream consumers (publisher thresholds, summarizer gating) may threshold it
directly. Calibration **regression** is *flagged* in the backtest verdict, **not
blocked** (soft gate; hardening deferred).

---

## Layer ownership rule

Each layer owns its own config; **no file is shared across a layer boundary.**

- `classifier.yml` / `fusion.yml` / the bundle — fastclass's.
- `govbot.yml` (the manifest: `datasets` / `transforms` / `publish` / `pipelines`) —
  govbot's. It has **no `tags:`**.
- A userland repo merely *contains* both — it owns neither tool's internals.
