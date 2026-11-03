'use strict';

/**
 * Pure, offline-testable helpers for the govbot npm wrapper.
 *
 * Platform/asset knowledge mirrors
 * `actions/govbot/scripts/install-nightly.sh` and the asset names published
 * by `.github/workflows/release-nightly.yml`.
 */

const path = require('node:path');

const DEFAULT_REPO = 'chihacknight/govbot';

/**
 * Ordered candidate release assets for a Node `process.platform` /
 * `process.arch` pair. The first entry is the primary asset; the rest are
 * fallbacks tried in order (same philosophy as install-nightly.sh, which
 * falls back between the macOS builds).
 *
 * @returns {string[]} asset file names, e.g. `govbot-linux-x86_64`
 * @throws {Error} with `code === 'UNSUPPORTED_PLATFORM'` when unknown
 */
function resolveAssets({ platform, arch }) {
  const key = `${platform}/${arch}`;
  const table = {
    // Built by release-nightly.yml.
    'linux/x64': ['govbot-linux-x86_64'],
    'darwin/arm64': ['govbot-macos-arm64', 'govbot-macos-x86_64'],
    // Apple Silicon under Rosetta reports x64; the native arm64 build works.
    'darwin/x64': ['govbot-macos-x86_64', 'govbot-macos-arm64'],
    // Published manually; see install-nightly.sh.
    'win32/x64': ['govbot-windows-x86_64.exe'],
  };
  const assets = table[key];
  if (!assets) {
    const err = new Error(
      `Unsupported platform for the govbot binary: ${key}. ` +
        'See https://github.com/chihacknight/govbot/releases for available builds, ' +
        'or point GOVBOT_BINARY_PATH at a local `cargo build --release --bin govbot` binary.',
    );
    err.code = 'UNSUPPORTED_PLATFORM';
    throw err;
  }
  return assets;
}

/** Binary file name inside the vendor directory. */
function binaryFileName({ platform }) {
  return platform === 'win32' ? 'govbot.exe' : 'govbot';
}

/** Absolute path of the vendored binary for this package install. */
function binaryPath({ packageDir, platform }) {
  return path.join(packageDir, 'vendor', binaryFileName({ platform }));
}

/** `https://github.com/<repo>/releases/download/<tag>/<asset>` */
function releaseDownloadUrl({ repo = DEFAULT_REPO, tag, asset }) {
  return `https://github.com/${repo}/releases/download/${tag}/${asset}`;
}

/**
 * Which release tag to download. Explicit `GOVBOT_TAG` wins (use `nightly`
 * for the bleeding edge); otherwise the versioned tag matching the package.
 */
function resolveTag({ packageVersion, tagEnv }) {
  if (tagEnv && tagEnv.length > 0) return tagEnv;
  return `v${packageVersion}`;
}

/** Package version, overridable via `GOVBOT_VERSION` for testing/RCs. */
function resolveVersion({ packageVersion, versionEnv }) {
  if (versionEnv && versionEnv.length > 0) return versionEnv;
  return packageVersion;
}

module.exports = {
  DEFAULT_REPO,
  resolveAssets,
  binaryFileName,
  binaryPath,
  releaseDownloadUrl,
  resolveTag,
  resolveVersion,
};
