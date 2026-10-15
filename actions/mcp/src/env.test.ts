/**
 * Tests for reading path settings from the environment, as the one-file Claude
 * Desktop install passes them (see env.ts for what arrives and why).
 */

import assert from "node:assert/strict";
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";

import { pathFromEnv } from "./env.js";
import { resolveBinary } from "./govbot.js";
import { workspacePath } from "./workspace.js";

const saved = { ...process.env };
let home: string;

beforeEach(() => {
  // os.homedir() reads HOME on macOS and Linux, so nothing touches the real one.
  home = mkdtempSync(join(tmpdir(), "govbot-env-test-"));
  process.env.HOME = home;
  process.env.USERPROFILE = home;
});

afterEach(() => {
  // Restored in place: replacing process.env with a plain object would detach it
  // from the real environment that os.homedir() reads.
  for (const key of ["HOME", "USERPROFILE", "GOVBOT_WORKSPACE", "GOVBOT_BIN"]) {
    if (saved[key] === undefined) delete process.env[key];
    else process.env[key] = saved[key];
  }
  rmSync(home, { recursive: true, force: true });
});

test("a blank or unsubstituted setting counts as unset", () => {
  for (const value of ["", "   ", "${user_config.workspace}", "${DOCUMENTS}/govbot"]) {
    process.env.GOVBOT_WORKSPACE = value;
    assert.equal(pathFromEnv("GOVBOT_WORKSPACE"), undefined, JSON.stringify(value));
  }
  delete process.env.GOVBOT_WORKSPACE;
  assert.equal(pathFromEnv("GOVBOT_WORKSPACE"), undefined);
});

test("a leading ~, $HOME or ${HOME} is the home directory", () => {
  for (const value of ["~/govbot-workspace", "$HOME/govbot-workspace", "${HOME}/govbot-workspace"]) {
    process.env.GOVBOT_WORKSPACE = value;
    assert.equal(pathFromEnv("GOVBOT_WORKSPACE"), join(home, "govbot-workspace"), value);
  }
  process.env.GOVBOT_WORKSPACE = "${HOME}";
  assert.equal(pathFromEnv("GOVBOT_WORKSPACE"), home);
});

test("other paths pass through untouched", () => {
  for (const value of ["/srv/govbot", "~other/govbot", "$HOMEDIR/govbot", "relative/dir"]) {
    process.env.GOVBOT_WORKSPACE = value;
    // `$HOMEDIR` has no `${`, so it is not a placeholder from the manifest.
    assert.equal(pathFromEnv("GOVBOT_WORKSPACE"), value);
  }
});

test("the workspace Claude Desktop's default passes is ~/govbot-workspace", () => {
  process.env.GOVBOT_WORKSPACE = "${HOME}/govbot-workspace";
  assert.equal(workspacePath(), join(home, "govbot-workspace"));
  process.env.GOVBOT_WORKSPACE = "";
  assert.equal(workspacePath(), join(home, "govbot-workspace"));
});

test("an empty GOVBOT_BIN falls back to ~/.govbot/bin, then PATH", () => {
  process.env.GOVBOT_BIN = "";
  assert.equal(resolveBinary(), "govbot");

  const bin = join(home, ".govbot", "bin");
  mkdirSync(bin, { recursive: true });
  writeFileSync(join(bin, "govbot"), "#!/bin/sh\n");
  chmodSync(join(bin, "govbot"), 0o755);
  assert.equal(resolveBinary(), join(bin, "govbot"));

  process.env.GOVBOT_BIN = "${user_config.govbot_binary}";
  assert.equal(resolveBinary(), join(bin, "govbot"));
});
