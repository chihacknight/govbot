'use strict';

/**
 * Keep `actions/govbot/npm/package.json` version in sync with
 * `actions/govbot/Cargo.toml` (`[package] version`).
 *
 *   node scripts/sync-version.js          # copy Cargo.toml version into package.json
 *   node scripts/sync-version.js --check  # exit 1 when they differ (CI)
 */

const fs = require('node:fs');
const path = require('node:path');

const NPM_DIR = path.join(__dirname, '..');
const CARGO_TOML = path.join(NPM_DIR, '..', 'Cargo.toml');
const PACKAGE_JSON = path.join(NPM_DIR, 'package.json');

function readCargoVersion() {
  const text = fs.readFileSync(CARGO_TOML, 'utf8');
  const match = text.match(/^version\s*=\s*"([^"]+)"\s*$/m);
  if (!match) throw new Error(`No [package] version found in ${CARGO_TOML}`);
  return match[1];
}

function main(argv) {
  const check = argv.includes('--check');
  const cargoVersion = readCargoVersion();
  const pkg = JSON.parse(fs.readFileSync(PACKAGE_JSON, 'utf8'));

  if (pkg.version === cargoVersion) {
    process.stderr.write(`[sync-version] in sync: ${pkg.version}\n`);
    return 0;
  }
  if (check) {
    process.stderr.write(
      `[sync-version] MISMATCH: package.json ${pkg.version} != Cargo.toml ${cargoVersion}\n` +
        '[sync-version] Run `npm run sync-version` in actions/govbot/npm and commit the result.\n',
    );
    return 1;
  }
  pkg.version = cargoVersion;
  fs.writeFileSync(PACKAGE_JSON, `${JSON.stringify(pkg, null, 2)}\n`);
  process.stderr.write(`[sync-version] bumped package.json to ${cargoVersion}\n`);
  return 0;
}

if (require.main === module) {
  process.exit(main(process.argv.slice(2)));
} else {
  module.exports = { main, readCargoVersion };
}
