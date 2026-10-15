/**
 * This server's version, and the oldest `govbot` CLI it works with.
 *
 * Both come from `package.json`, the single source of truth: the release
 * workflow publishes them in `govbot-mcp-version.json`, and
 * `scripts/build-bundle.sh` refuses to build if `mcpb/manifest.json` disagrees.
 *
 * `package.json` sits in a different place relative to this file depending on
 * how the server is run: `dist/../package.json` from a checkout, and
 * `server/package.json` inside the `.mcpb` bundle (build-bundle.sh copies it
 * there). Both are tried, and the name is checked so an unrelated package.json
 * is never mistaken for ours.
 */

import { readFileSync } from "node:fs";

interface PackageInfo {
  version: string;
  cliMin: string | null;
}

function readPackage(): PackageInfo {
  for (const relative of ["./package.json", "../package.json"]) {
    try {
      const pkg = JSON.parse(readFileSync(new URL(relative, import.meta.url), "utf8"));
      if (pkg?.name === "@govbot/mcp" && typeof pkg.version === "string") {
        const cliMin = pkg.govbot?.cliMin;
        return { version: pkg.version, cliMin: typeof cliMin === "string" ? cliMin : null };
      }
    } catch {
      // Not there in this layout; try the next one.
    }
  }
  // Unknown rather than a made-up number: an unparseable version never
  // produces an update notice, whereas "0.0.0" would always produce one.
  process.stderr.write("[govbot-mcp] could not read package.json; version unknown\n");
  return { version: "unknown", cliMin: null };
}

const PACKAGE = readPackage();

export const SERVER_VERSION = PACKAGE.version;

/**
 * The oldest CLI this server works with.
 *
 * Caveat: the nightly CLI's `--version` only moves when `actions/govbot/Cargo.toml`
 * is bumped, so raising this is only meaningful together with such a bump.
 */
export const CLI_MIN = PACKAGE.cliMin;
