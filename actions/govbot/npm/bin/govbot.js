#!/usr/bin/env node
'use strict';

/**
 * `govbot` bin shim: exec the platform binary vendored by postinstall.
 * All args, stdio, and the exit code pass straight through, so pipes like
 * `govbot logs | govbot tag` behave exactly like the native binary.
 *
 * `GOVBOT_BINARY_PATH` overrides the vendored binary (local cargo builds).
 */

const fs = require('node:fs');
const { spawnSync } = require('node:child_process');
const { binaryPath } = require('../helpers/platform');

function resolveBinary() {
  if (process.env.GOVBOT_BINARY_PATH && process.env.GOVBOT_BINARY_PATH.length > 0) {
    return process.env.GOVBOT_BINARY_PATH;
  }
  return binaryPath({ packageDir: require('node:path').join(__dirname, '..'), platform: process.platform });
}

function main(argv) {
  const bin = resolveBinary();
  if (!fs.existsSync(bin)) {
    process.stderr.write(
      'govbot: binary not found. The postinstall download probably failed or was skipped.\n' +
        `Looked for: ${bin}\n` +
        'Fix: `npm rebuild govbot` (or reinstall), or set GOVBOT_BINARY_PATH to a local\n' +
        '`cargo build --release --bin govbot` binary. See https://github.com/chihacknight/govbot/releases\n',
    );
    return 1;
  }
  const result = spawnSync(bin, argv, { stdio: 'inherit' });
  if (result.error) {
    process.stderr.write(`govbot: failed to run ${bin}: ${result.error.message}\n`);
    return 1;
  }
  return result.status ?? 1;
}

if (require.main === module) {
  process.exit(main(process.argv.slice(2)));
} else {
  module.exports = { main, resolveBinary };
}
