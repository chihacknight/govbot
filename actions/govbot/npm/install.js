'use strict';

/**
 * postinstall: fetch the prebuilt govbot binary from GitHub releases into
 * `<package>/vendor/`. Zero runtime dependencies (stdlib only).
 *
 * Environment overrides:
 *   GOVBOT_SKIP_DOWNLOAD=1  skip (offline CI / `npm install --ignore-scripts` equivalent)
 *   GOVBOT_BINARY_URL=<url> download this exact file instead
 *   GOVBOT_BINARY_PATH=<path> copy a local binary (e.g. cargo target dir) instead
 *   GOVBOT_TAG=<tag>       release tag (default: `v<package version>`, e.g. `v0.1.0`)
 *   GOVBOT_VERSION=<x.y.z>  override the version used for the default tag
 *   GOVBOT_REPO=<org/repo>  override the GitHub repo (default: chihacknight/govbot)
 */

const fs = require('node:fs');
const https = require('node:https');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const {
  DEFAULT_REPO,
  resolveAssets,
  binaryPath,
  releaseDownloadUrl,
  resolveTag,
  resolveVersion,
} = require('./helpers/platform');

const PACKAGE_DIR = __dirname;
const VENDOR_DIR = path.join(PACKAGE_DIR, 'vendor');

function log(msg) {
  process.stderr.write(`[govbot postinstall] ${msg}\n`);
}

/** GET with redirect-following (releases/download redirects to object storage). */
function download(url, dest, redirectsLeft = 5) {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      { headers: { 'User-Agent': 'govbot-npm-installer' } },
      (res) => {
        const { statusCode, headers } = res;
        if (statusCode >= 300 && statusCode < 400 && headers.location) {
          res.resume();
          if (redirectsLeft <= 0) {
            reject(new Error(`Too many redirects downloading ${url}`));
            return;
          }
          download(headers.location, dest, redirectsLeft - 1).then(resolve, reject);
          return;
        }
        if (statusCode !== 200) {
          res.resume();
          const err = new Error(`Download failed: HTTP ${statusCode} for ${url}`);
          err.httpStatus = statusCode;
          reject(err);
          return;
        }
        const out = fs.createWriteStream(dest, { mode: 0o755 });
        res.pipe(out);
        out.on('finish', () => resolve());
        out.on('error', reject);
        res.on('error', reject);
      },
    );
    req.on('error', reject);
    req.end();
  });
}

async function main() {
  if (process.env.GOVBOT_SKIP_DOWNLOAD === '1') {
    log('GOVBOT_SKIP_DOWNLOAD=1, skipping binary download.');
    return;
  }

  const dest = binaryPath({ packageDir: PACKAGE_DIR, platform: process.platform });
  fs.mkdirSync(VENDOR_DIR, { recursive: true });

  // Local binary override (fast path for contributors with a cargo build).
  if (process.env.GOVBOT_BINARY_PATH) {
    const src = process.env.GOVBOT_BINARY_PATH;
    fs.copyFileSync(src, dest);
    if (process.platform !== 'win32') fs.chmodSync(dest, 0o755);
    log(`Installed local binary from ${src}`);
    return;
  }

  // Exact URL override (air-gapped mirrors, release testing).
  if (process.env.GOVBOT_BINARY_URL) {
    log(`Downloading ${process.env.GOVBOT_BINARY_URL}`);
    await download(process.env.GOVBOT_BINARY_URL, dest);
    if (process.platform !== 'win32') fs.chmodSync(dest, 0o755);
    return;
  }

  const pkg = JSON.parse(fs.readFileSync(path.join(PACKAGE_DIR, 'package.json'), 'utf8'));
  const repo = process.env.GOVBOT_REPO || DEFAULT_REPO;
  const version = resolveVersion({ packageVersion: pkg.version, versionEnv: process.env.GOVBOT_VERSION });
  const tag = resolveTag({ packageVersion: version, tagEnv: process.env.GOVBOT_TAG });
  const assets = resolveAssets({ platform: process.platform, arch: process.arch });
  const tried = [];

  for (const asset of assets) {
    const url = releaseDownloadUrl({ repo, tag, asset });
    log(`Downloading ${url}`);
    try {
      // eslint-disable-next-line no-await-in-loop
      await download(url, dest);
      if (process.platform !== 'win32') fs.chmodSync(dest, 0o755);
      log(`Installed govbot ${tag} (${asset})`);
      return;
    } catch (err) {
      tried.push(`${asset} (${err.message})`);
      // Only fall through to the next asset on 404; anything else is fatal
      // (network down, auth issue) so we fail loudly instead of installing
      // the wrong thing.
      if (err.httpStatus !== 404) throw err;
      log(`Not found, trying next asset: ${asset}`);
    }
  }

  // Versioned tag missing entirely (e.g. no release cut yet): fall back to
  // the rolling `nightly` release, matching install-nightly.sh behaviour.
  if (tag !== 'nightly' && !process.env.GOVBOT_TAG) {
    log(`No ${tag} release found; falling back to the nightly release.`);
    for (const asset of assets) {
      const url = releaseDownloadUrl({ repo, tag: 'nightly', asset });
      log(`Downloading ${url}`);
      try {
        // eslint-disable-next-line no-await-in-loop
        await download(url, dest);
        if (process.platform !== 'win32') fs.chmodSync(dest, 0o755);
        log(`Installed govbot nightly (${asset})`);
        return;
      } catch (err) {
        tried.push(`nightly/${asset} (${err.message})`);
        if (err.httpStatus !== 404) throw err;
      }
    }
  }

  throw new Error(
    `Could not download a govbot binary for ${process.platform}/${process.arch}.\n` +
      `Tried:\n  - ${tried.join('\n  - ')}\n` +
      'Set GOVBOT_BINARY_URL to a direct download, GOVBOT_BINARY_PATH to a local ' +
      '`cargo build --release --bin govbot` binary, or GOVBOT_TAG=nightly to try the nightly build.',
  );
}

// Allow `node install.js --check` style probes without side effects in tests.
if (require.main === module) {
  main().catch((err) => {
    process.stderr.write(`[govbot postinstall] ERROR: ${err.message}\n`);
    process.exit(1);
  });
} else {
  module.exports = { main, download };
}
