# The govbot dataset registry

govbot resolves datasets at **runtime** through a registry — an index that
maps a dataset identifier to the git repo holding its data. This is the
"npm/docker for government data" layer: it replaces the old compiled
52-variant `WorkingLocale` enum, so adding counties, cities, or agencies is a
data change, not a recompile.

## Identifier scheme

A canonical identifier is `namespace/name[@channel]`:

| Part | Meaning |
|---|---|
| `namespace` | a grouping — `us-legislation`, a county set, an agency set |
| `name` | the dataset within the namespace — `wy`, `il`, … |
| `@channel` | optional release channel / git branch (defaults to the repo's default branch) |

**Plain jurisdiction codes stay valid.** A bare identifier with no `/` (e.g.
`wy`) is resolved against the registry's `default_namespace`, so an existing
`govbot.yml` with `datasets: [wy]` keeps working unchanged. `all` is a
reserved alias meaning "every dataset in the registry."

Examples — all valid in `govbot.yml` / `govbot add` / `govbot pull`:

```
wy                       # bare code -> us-legislation/wy
us-legislation/wy        # canonical
us-legislation/wy@main   # pinned to a channel/branch
all                      # every dataset
```

## File format

The registry is a JSON file. The bundled default lives at
`actions/govbot/data/registry.json` and is **compiled into the binary** via
`include_str!`, so a fresh install resolves the seed jurisdictions with zero
network access.

```json
{
  "$schema_version": "govbot-registry-1",
  "description": "…",
  "default_namespace": "us-legislation",
  "datasets": {
    "us-legislation/wy": {
      "git_url": "https://github.com/chn-openstates-files/wy-legislation.git",
      "schema": "ocdfiles",
      "path_pattern": "**/logs/*.json",
      "name": "Wyoming"
    }
  }
}
```

Per-dataset fields:

| Field | Required | Meaning |
|---|---|---|
| `git_url` | yes | the git repo the dataset's data is cloned from |
| `schema` | no | the data schema the dataset follows (e.g. `ocdfiles`) |
| `path_pattern` | no | a glob, relative to the repo root, locating the dataset's records |
| `name` | no | a human-readable display name |

## Where the registry comes from / how it is fetched

`Registry::load` resolves the active registry in priority order:

1. **`GOVBOT_REGISTRY_URL`** — an `http(s)://` URL (fetched over HTTP) or a
   local file path. A fetched registry is cached at `~/.govbot/registry.json`.
2. **`<project>/.govbot/registry.json`** — a project-local registry file.
3. **The bundled default** compiled into the binary.

This makes the registry both a shipped default and a fetchable/overridable
catalog — an open, PR-based registry repo or a hosted catalog can both be
pointed at via `GOVBOT_REGISTRY_URL`.

## `govbot.lock` — the dataset lockfile

`govbot.yml` declares *which* datasets a project wants; `govbot.lock` records
the *exact git commit* each resolved to. It is govbot's `Cargo.lock`.

- **Written/updated** by `govbot pull` and `govbot run`, next to `govbot.yml`.
- **Format** — JSON; see `src/lock.rs`. Each entry pins `git_url`, `channel`,
  `commit`, `cache_key`, and `resolved_at`.
- **Commit it** to the project repo for reproducible runs.

## The shared content-addressed cache

A dataset is cloned **once per machine** into `~/.govbot/cache/<key>`, where
`<key>` is `<short_name>-<sha256(git_url@channel)[..12]>`. A project's
`.govbot/repos/<name>` is a symlink into that cache. A second `pull` — in this
or any other project — finds the cache populated and only fetches deltas. See
`src/cache.rs`.
