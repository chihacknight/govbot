/**
 * Tests for editing `govbot.yml`.
 *
 * The file is the person's: they are told to open and edit it. These check that
 * saving topics or recording a clone never destroys what they wrote, whether
 * that is a comment, a key this server does not know about, or a file with a
 * typo in it.
 */

import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";
import { parse } from "yaml";

import { saveValues } from "./tools.js";
import * as workspace from "./workspace.js";

let dir: string;

beforeEach(async () => {
  // A throwaway workspace; never the person's real ~/govbot-workspace.
  dir = await mkdtemp(join(tmpdir(), "govbot-mcp-test-"));
  process.env.GOVBOT_WORKSPACE = dir;
});

afterEach(async () => {
  delete process.env.GOVBOT_WORKSPACE;
  await rm(dir, { recursive: true, force: true });
});

const transit = { description: "Public transit funding and service.", threshold: 0.72 };

// A tab used as indentation: an easy slip when editing by hand.
const BROKEN = "repos:\n  - il\ntags:\n  housing:\n\tdescription: Rent stabilization.\n";

test("a govbot.yml that does not parse is never overwritten", async () => {
  await writeFile(workspace.configPath(), BROKEN, "utf8");

  await assert.rejects(workspace.saveTags({ transit }), (error: unknown) => {
    assert.ok(error instanceof workspace.ConfigError);
    assert.match(error.message, /govbot\.yml/);
    assert.match(error.message, /line 5, column 1/);
    return true;
  });
  await assert.rejects(workspace.addRepos(["usa"]), workspace.ConfigError);

  assert.equal(await readFile(workspace.configPath(), "utf8"), BROKEN);
});

test("save_my_values reports a broken govbot.yml instead of replacing it", async () => {
  await writeFile(workspace.configPath(), BROKEN, "utf8");

  const result = await saveValues({
    topics: [{ name: "transit", ...transit, include_keywords: ["transit"] }],
  });

  assert.equal(result.isError, true);
  assert.match(result.text, /Did not save transit/);
  assert.match(result.text, /line 5, column 1/);
  assert.equal(await readFile(workspace.configPath(), "utf8"), BROKEN);
});

test("comments and unknown keys survive saving topics and recording clones", async () => {
  const original = [
    "# My notes: started this for the tenants union.",
    "repos:",
    "  - il # home state",
    "tags:",
    "  housing:",
    "    description: Rent stabilization.",
    "    threshold: 0.72",
    "# Shared with the transit working group.",
    "owner: maria",
    "",
  ].join("\n");
  await writeFile(workspace.configPath(), original, "utf8");

  assert.deepEqual(await workspace.saveTags({ transit }), ["housing", "transit"]);
  assert.deepEqual(await workspace.addRepos(["usa", "IL"]), ["il", "usa"]);

  const text = await readFile(workspace.configPath(), "utf8");
  assert.match(text, /# My notes: started this for the tenants union\./);
  assert.match(text, /- il # home state/);
  assert.match(text, /# Shared with the transit working group\./);

  const parsed = parse(text);
  assert.equal(parsed.owner, "maria");
  assert.deepEqual(parsed.repos, ["il", "usa"]);
  assert.deepEqual(Object.keys(parsed.tags), ["housing", "transit"]);
  assert.deepEqual(parsed.tags.transit, transit);
});

test("saving a topic with an existing name replaces only that topic", async () => {
  await workspace.saveTags({ transit, housing: { description: "Rent." } });
  await workspace.saveTags({ transit: { description: "Buses only." } });

  const parsed = parse(await readFile(workspace.configPath(), "utf8"));
  assert.deepEqual(parsed.tags, {
    transit: { description: "Buses only." },
    housing: { description: "Rent." },
  });
});

test("a missing govbot.yml still means start fresh", async () => {
  assert.deepEqual(await workspace.addRepos(["il"]), ["il"]);

  const text = await readFile(workspace.configPath(), "utf8");
  assert.match(text, /^# Your govbot project\./);
  // Grows into a normal block list, not an inline `[ il ]`.
  assert.match(text, /^repos:\n {2}- il$/m);
  assert.deepEqual(parse(text).tags, {});
});

test("a repos entry that is not a list is reported, not replaced", async () => {
  const original = "repos: il\ntags: {}\n";
  await writeFile(workspace.configPath(), original, "utf8");

  await assert.rejects(workspace.addRepos(["usa"]), /`repos` is not a list/);
  assert.equal(await readFile(workspace.configPath(), "utf8"), original);
});

test("an empty repos or tags entry is treated as an empty list", async () => {
  await writeFile(workspace.configPath(), "# mine\nrepos:\ntags:\nextra: 1\n", "utf8");

  assert.deepEqual(await workspace.addRepos(["il"]), ["il"]);
  assert.deepEqual(await workspace.saveTags({ transit }), ["transit"]);

  const text = await readFile(workspace.configPath(), "utf8");
  assert.match(text, /^# mine$/m);
  assert.deepEqual(parse(text), { repos: ["il"], tags: { transit }, extra: 1 });
});
