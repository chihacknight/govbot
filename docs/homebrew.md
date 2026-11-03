# Installing govbot with Homebrew (issue #19)

Homebrew formulae live in homebrew-core (a separate repository), so this repo
cannot grant `brew install govbot` by itself. What it *can* do — and what this
branch adds — is everything a formula needs: versioned GitHub releases with
bottled binaries, plus a ready-to-use formula template.

## Install today (tap-less, from this repo)

Prerequisite: one versioned release must exist (see "Cutting a release"
below). Then:

```bash
brew install https://raw.githubusercontent.com/chihacknight/govbot/main/Formula/govbot.rb
govbot --help
```

Optional, only for `govbot load` (SQL analysis of cloned data):

```bash
brew install duckdb
```

> Avoid `govbot update` on a Homebrew install — it overwrites the managed
> binary with a nightly build. Use `brew upgrade govbot` instead.

## Cutting a release (maintainers)

1. Bump `version` in `actions/govbot/Cargo.toml` (run `cargo build` in
   `actions/govbot` to refresh `Cargo.lock`).
2. Tag and push: `git tag govbot-vX.Y.Z && git push origin govbot-vX.Y.Z`.
3. `.github/workflows/release.yml` verifies the tag matches `Cargo.toml`,
   builds bottled tarballs for macOS arm64, macOS x86_64, and Linux x86_64,
   and publishes the GitHub Release with a `SHA256SUMS` file.
4. Copy the three tarball checksums from `SHA256SUMS` into `Formula/govbot.rb`
   (replace the `REPLACE_WITH_SHA256_FROM_RELEASE_SHA256SUMS` placeholders)
   and bump `version` plus the download URLs. Commit that as part of the
   release.

Verify a bottle without installing:

```bash
curl -fsSL -o govbot.tar.gz <release tarball URL>
echo "<sha256 from SHA256SUMS>  govbot.tar.gz" | sha256sum -c -
tar tzf govbot.tar.gz   # expect a single `govbot` binary
```

## Submitting to homebrew-core (`brew install govbot` with no URL)

Next steps, in order:

1. **Adopt a license.** The repo currently declares none (no `LICENSE` file,
   no `license` in `Cargo.toml`). homebrew-core requires an SPDX `license`
   line; pick one (e.g. MIT), add the file, and uncomment the `license` line
   in `Formula/govbot.rb`.
2. **Go from-source.** homebrew-core builds from the source tarball instead
   of prebuilt bottles: replace the per-OS `url`/`sha256` blocks with
   `url "https://github.com/chihacknight/govbot/archive/refs/tags/govbot-vX.Y.Z.tar.gz"`,
   add `depends_on "rust" => :build` (plus `pkg-config`, `openssl@3`,
   `libssh2`, `zlib` for the `git2` crate's system libs), and an
   `install` that runs `cargo install --locked --root #{prefix} --path actions/govbot`.
   Known wrinkle: the `ort` dependency downloads its ONNX Runtime binary from
   the network at build time, which the homebrew-core sandbox forbids — that
   needs a vendored/offline solution first.
3. **Audit and propose:** `brew audit --new govbot`, `brew test govbot`,
   then open a PR against `homebrew/homebrew-core` bottle-naming it `govbot`.
