'use strict';

// Offline tests for the npm wrapper's pure logic (no network, no binary).
// Run: `node --test test/` from actions/govbot/npm (or `npm test`).

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const {
  resolveAssets,
  binaryFileName,
  binaryPath,
  releaseDownloadUrl,
  resolveTag,
  resolveVersion,
} = require('../helpers/platform');

describe('resolveAssets', () => {
  it('maps linux/x64 to the linux release asset', () => {
    assert.deepEqual(resolveAssets({ platform: 'linux', arch: 'x64' }), ['govbot-linux-x86_64']);
  });

  it('maps darwin/arm64 to the macOS arm64 asset first', () => {
    const assets = resolveAssets({ platform: 'darwin', arch: 'arm64' });
    assert.equal(assets[0], 'govbot-macos-arm64');
  });

  it('maps darwin/x64 (Rosetta) with an arm64 fallback', () => {
    assert.deepEqual(resolveAssets({ platform: 'darwin', arch: 'x64' }), [
      'govbot-macos-x86_64',
      'govbot-macos-arm64',
    ]);
  });

  it('maps win32/x64 to the windows exe asset', () => {
    assert.deepEqual(resolveAssets({ platform: 'win32', arch: 'x64' }), [
      'govbot-windows-x86_64.exe',
    ]);
  });

  it('throws UNSUPPORTED_PLATFORM with a helpful message otherwise', () => {
    assert.throws(() => resolveAssets({ platform: 'linux', arch: 'arm64' }), (err) => {
      assert.equal(err.code, 'UNSUPPORTED_PLATFORM');
      assert.match(err.message, /linux\/arm64/);
      assert.match(err.message, /GOVBOT_BINARY_PATH/);
      return true;
    });
  });
});

describe('binaryFileName / binaryPath', () => {
  it('uses .exe on Windows only', () => {
    assert.equal(binaryFileName({ platform: 'win32' }), 'govbot.exe');
    assert.equal(binaryFileName({ platform: 'linux' }), 'govbot');
    assert.equal(binaryFileName({ platform: 'darwin' }), 'govbot');
  });

  it('vendors under <package>/vendor/', () => {
    const join = require('node:path').join;
    assert.equal(
      binaryPath({ packageDir: `${join('/pkg')}`, platform: 'linux' }),
      join('/pkg', 'vendor', 'govbot'),
    );
    assert.equal(
      binaryPath({ packageDir: `${join('/pkg')}`, platform: 'win32' }),
      join('/pkg', 'vendor', 'govbot.exe'),
    );
  });
});

describe('releaseDownloadUrl', () => {
  it('builds the GitHub releases download URL', () => {
    assert.equal(
      releaseDownloadUrl({ repo: 'chihacknight/govbot', tag: 'v0.1.0', asset: 'govbot-linux-x86_64' }),
      'https://github.com/chihacknight/govbot/releases/download/v0.1.0/govbot-linux-x86_64',
    );
  });
});

describe('resolveTag / resolveVersion', () => {
  it('defaults to the v<version> tag', () => {
    assert.equal(resolveTag({ packageVersion: '0.1.0' }), 'v0.1.0');
  });

  it('GOVBOT_TAG wins (e.g. nightly)', () => {
    assert.equal(resolveTag({ packageVersion: '0.1.0', tagEnv: 'nightly' }), 'nightly');
  });

  it('GOVBOT_VERSION overrides the package version', () => {
    assert.equal(
      resolveVersion({ packageVersion: '0.1.0', versionEnv: '0.2.0' }),
      '0.2.0',
    );
    assert.equal(resolveVersion({ packageVersion: '0.1.0' }), '0.1.0');
  });
});
