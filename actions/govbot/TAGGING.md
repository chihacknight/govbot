# Classifying and tagging bills

govbot does **not** classify bills itself. Classification is delegated to
**fastclass**, a standalone, self-improving text classifier that runs as an
external transform. govbot streams documents in, fastclass classifies them, and
`govbot apply` persists the results.

## The pipe

```bash
govbot source --select docs | fastclass classify - classifier=./classifier | govbot apply
```

- **`govbot source --select docs`** emits one `{"id","text","kind":"docs"}`
  document per bill carrying the **full bill text** from `metadata.json`. The
  `id` is the bill's dataset path, which routes the result back to the right
  place.
- **`fastclass classify -`** scores each document against a **classifier
  bundle** — a fastclass-native directory (`classifier.yml` + `fusion.yml` +
  `eval/`). govbot passes only the bundle path; it never reads the bundle.
- **`govbot apply`** reads fastclass's result JSON from stdin and writes per-tag
  `.tag.json` files into the dataset. It classifies nothing — it is purely the
  persistence sink. `govbot publish` later turns those files into feeds.

`govbot run` (or bare `govbot`) orchestrates this whole pipe automatically from
the manifest's `transforms:`/`pipelines:`.

## The manifest declares the transform — not the taxonomy

`govbot.yml` is a project **manifest**. It has **no `tags:` block**. The
classify transform is declared under `transforms:` and points at a fastclass
classifier bundle by path:

```yaml
transforms:
  classify:
    command: [fastclass, classify, "-"]
    reads: docs
    writes: classification
    classifier: ./classifier   # path to the fastclass bundle (classifier.yml)
```

The tag taxonomy — descriptions, examples, keywords, thresholds, fusion
weights — lives entirely inside the fastclass classifier bundle's
`classifier.yml`, owned and versioned separately. See the fastclass docs and
its Claude Code plugin (`/fastclass:improve`, `/fastclass:ratify`) for building
and improving a bundle.

## Prerequisite

The `fastclass` binary must be resolvable on `PATH`, `~/.cargo/bin`, or
`~/.govbot/bin`:

```bash
cd <fastclass repo> && cargo install --path .
```

govbot's transform runner resolves transform binaries the same way.

## Output

`govbot apply` writes per-tag files under each session's `tags/` directory:

```text
country:us/state:{state}/sessions/{session_id}/tags/{tag_name}.tag.json
```

Each `{tag_name}.tag.json` file contains:

- `metadata`: classifier info, last-run timestamp, tag-config hash
- `tag_config`: a stub tag definition (the real taxonomy lives in the bundle)
- `text_cache`: deduplicated bill texts keyed by content hash
- `bills`: a map of bill identifiers to their `ScoreBreakdown`

`ScoreBreakdown.final_score` is fastclass's calibrated probability for the tag.
