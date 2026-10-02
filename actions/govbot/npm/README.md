# govbot (npm)

> `govbot` — streaming pipeline CLI for government legislative data.
> This package vendors the prebuilt Rust binary for your platform, so
> `npm install -g govbot` / `npx govbot` just works. No Rust toolchain needed.

Part of [chihacknight/govbot](https://github.com/chihacknight/govbot) —
the wrapper lives in [`actions/govbot/npm/`](https://github.com/chihacknight/govbot/tree/main/actions/govbot/npm).
Tracks issue [#20](https://github.com/chihacknight/govbot/issues/20).

## Install

```bash
npm install -g govbot
govbot --help

# or try it without installing
npx govbot --help
```

On first install (`postinstall`) the package downloads the matching prebuilt
binary from
[GitHub releases](https://github.com/chihacknight/govbot/releases) into its
own `vendor/` folder. If no versioned release matches the package version yet,
it falls back to the rolling `nightly` build — same as
[`install-nightly.sh`](../scripts/install-nightly.sh).

### Supported platforms

| OS | Arch | Asset |
| --- | --- | --- |
| Linux | x64 | `govbot-linux-x86_64` |
| macOS | arm64 (Apple Silicon) | `govbot-macos-arm64` |
| macOS | x64 (Intel / Rosetta) | `govbot-macos-x86_64`, falls back to arm64 |
| Windows | x64 | `govbot-windows-x86_64.exe` |

Anything else fails loudly at install time with directions (see overrides).

## Environment overrides

| Variable | Effect |
| --- | --- |
| `GOVBOT_TAG` | Release tag to download (default `v<package version>`; use `nightly` for bleeding edge) |
| `GOVBOT_VERSION` | Override the version used for the default tag |
| `GOVBOT_REPO` | Override the GitHub repo (`org/repo`, default `chihacknight/govbot`) |
| `GOVBOT_BINARY_URL` | Download this exact file instead of a release asset |
| `GOVBOT_BINARY_PATH` | Copy a local binary instead of downloading (e.g. your `cargo build --release --bin govbot` output); the `govbot` shim also honors it at runtime |
| `GOVBOT_SKIP_DOWNLOAD=1` | Skip the download (offline CI; the shim will error until a binary is provided) |

```bash
# Use a local cargo build instead of downloading
GOVBOT_BINARY_PATH=$PWD/../target/release/govbot npm install -g .
```

## For maintainers

- **Version sync:** the npm version must match `[package] version` in
  [`../Cargo.toml`](../Cargo.toml).
  `npm run sync-version` copies it over;
  `npm run check-version` (runs in CI) fails when they differ.
- **Tests:** `npm test` runs offline `node --test` suites in `test/` covering
  the platform/asset mapping and the bin shim. No network, no binary needed.
- **Publish:** `npm publish` from this directory (CI does it on
  `npm-govbot-v*` tags; see `.github/workflows/npm-govbot.yml`).
