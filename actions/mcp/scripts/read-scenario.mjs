#!/usr/bin/env node
/**
 * Print one field of a scenario file, for desktop-capture.sh.
 *
 *   node scripts/read-scenario.mjs scenarios/address-refusal.yml prompt
 *
 * Lists (e.g. `setup.jurisdictions`) print one item per line. A missing required
 * field is an error, so a typo in a scenario fails the capture instead of typing
 * "undefined" into Claude Desktop.
 */

import { readFileSync } from "node:fs";
import YAML from "yaml";

const [file, path] = process.argv.slice(2);
if (!file || !path) {
  process.stderr.write("usage: read-scenario.mjs <scenario.yml> <field[.sub]>\n");
  process.exit(2);
}

const scenario = YAML.parse(readFileSync(file, "utf8"));
for (const required of ["id", "prompt", "expect"]) {
  if (scenario?.[required] === undefined) {
    process.stderr.write(`${file}: missing required field "${required}"\n`);
    process.exit(1);
  }
}

let value = scenario;
for (const key of path.split(".")) value = value?.[key];

if (value === undefined || value === null) process.exit(0);
if (Array.isArray(value)) process.stdout.write(value.join("\n") + "\n");
else if (typeof value === "object") process.stdout.write(JSON.stringify(value) + "\n");
else process.stdout.write(String(value).trimEnd() + "\n");
