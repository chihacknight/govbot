# Tap-ready Homebrew formula for govbot.
#
# Homebrew formulae live in homebrew-core (a separate repo), so this file is
# the in-repo template that makes `brew install govbot` possible:
#   1. Cut a versioned release (`git tag govbot-vX.Y.Z`), which runs
#      .github/workflows/release.yml and publishes bottled tarballs.
#   2. Copy the SHA256 checksums from the release's SHA256SUMS file into the
#      placeholders below and bump `version` + the download URLs.
#   3. Install from this repo (no separate tap needed):
#        brew install https://raw.githubusercontent.com/chihacknight/govbot/main/Formula/govbot.rb
#
# Path to homebrew-core (`brew install govbot` with no URL) additionally needs:
#   - an SPDX `license` line. The repo currently declares NO license
#     (no LICENSE file, no `license` in Cargo.toml, GitHub license: none),
#     so maintainers must adopt one first (see issue #19);
#   - a from-source `install` (cargo build) instead of prebuilt bottles.
#     Known wrinkle: the `ort` dependency downloads its ONNX Runtime binary
#     at build time, which the homebrew-core sandbox forbids; that needs a
#     vendored/offline solution before a core submission will pass audit.
#     Until then, this bottle-based formula is the supported route.
#
# Runtime dependencies (checked against actions/govbot/src/main.rs):
#   - `duckdb` CLI: OPTIONAL, only used by `govbot load` (fails gracefully
#     with install instructions when missing). Intentionally NOT a hard
#     `depends_on` (homebrew-core forbids optional deps); see `caveats`.
#   - git access is via the `git2` crate (libgit2 built in) -- no `git`
#     formula dependency needed. No node/mcp runtime dependency exists.
class Govbot < Formula
  desc "CLI for distributed analysis of government legislative updates"
  homepage "https://github.com/chihacknight/govbot"
  version "0.1.0"

  # TODO: uncomment once upstream adopts a license (required by homebrew-core).
  # license ""

  on_macos do
    on_arm do
      url "https://github.com/chihacknight/govbot/releases/download/govbot-v0.1.0/govbot-macos-arm64.tar.gz"
      sha256 "REPLACE_WITH_SHA256_FROM_RELEASE_SHA256SUMS"
    end
    on_intel do
      url "https://github.com/chihacknight/govbot/releases/download/govbot-v0.1.0/govbot-macos-x86_64.tar.gz"
      sha256 "REPLACE_WITH_SHA256_FROM_RELEASE_SHA256SUMS"
    end
  end

  on_linux do
    url "https://github.com/chihacknight/govbot/releases/download/govbot-v0.1.0/govbot-linux-x86_64.tar.gz"
    sha256 "REPLACE_WITH_SHA256_FROM_RELEASE_SHA256SUMS"
  end

  livecheck do
    url :github_latest
    strategy :github_tag
    regex(/^govbot-v?(\d+(?:\.\d+)+)$/)
  end

  def install
    bin.install "govbot"
  end

  def caveats
    <<~EOS
      `govbot load` needs the DuckDB CLI (optional):
        brew install duckdb
      Manage upgrades with brew (`brew upgrade govbot`). Avoid `govbot update`
      on a Homebrew install -- it overwrites the binary with a nightly build.
    EOS
  end

  test do
    assert_match "govbot #{version}", shell_output("#{bin}/govbot --version")
    assert_match "Usage:", shell_output("#{bin}/govbot --help")
  end
end
