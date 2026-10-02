'use strict';

// Offline tests for the bin shim: missing-binary error and arg passthrough.
// Uses the running Node executable as a stand-in "govbot binary".

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const SHIM = path.join(__dirname, '..', 'bin', 'govbot.js');

function runShim(args, env) {
  return spawnSync(process.execPath, [SHIM, ...args], {
    env: { ...process.env, ...env },
    encoding: 'utf8',
  });
}

describe('bin/govbot.js', () => {
  it('exits 1 with a reinstall hint when the binary is missing', () => {
    const result = runShim(['--version'], {
      GOVBOT_BINARY_PATH: path.join(__dirname, 'does-not-exist-govbot'),
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /binary not found/);
    assert.match(result.stderr, /npm rebuild govbot/);
  });

  it('passes args through and forwards the exit code', () => {
    const result = runShim(['-e', 'process.exit(42)'], {
      GOVBOT_BINARY_PATH: process.execPath,
    });
    assert.equal(result.status, 42);
  });

  it('passes stdout through untouched', () => {
    const result = runShim(['-e', 'process.stdout.write("hello-pipe")'], {
      GOVBOT_BINARY_PATH: process.execPath,
    });
    assert.equal(result.status, 0);
    assert.equal(result.stdout, 'hello-pipe');
  });
});
