/**
 * Reading path settings from the environment.
 *
 * The one-file Claude Desktop install passes its settings as environment
 * variables built from the manifest's `user_config`, and what arrives is not
 * always a usable path:
 *
 * - Claude Desktop substitutes `${user_config.workspace}` in a single pass, so
 *   a default of `"${HOME}/govbot-workspace"` reaches the server with `${HOME}`
 *   still in it. (Seen live, 2026-10-15: `mkdir '${HOME}'`. The reference
 *   implementation in @anthropic-ai/mcpb 2.1.2, `getMcpConfigForManifest`,
 *   does the same.)
 * - A setting with no default and no value is not substituted at all, so the
 *   server sees the literal text `${user_config.workspace}`.
 * - A blank setting arrives as `""`.
 *
 * None of these is something the person chose, so all of them mean "use the
 * default" rather than an error.
 */

import { homedir } from "node:os";
import { join } from "node:path";

/**
 * A path from the environment, or `undefined` when there is no usable one.
 *
 * A leading `~`, `$HOME` or `${HOME}` is expanded to the home directory, since
 * nothing else will do it: the server is started without a shell. Anything
 * still holding `${` after that is an unsubstituted placeholder and is treated
 * as unset.
 */
export function pathFromEnv(name: string): string | undefined {
  const raw = process.env[name]?.trim();
  if (!raw) return undefined;

  const expanded = expandHome(raw);
  if (expanded.includes("${")) return undefined;
  return expanded;
}

function expandHome(value: string): string {
  // Only a whole leading segment: `~user/...` and `$HOMEDIR` are left alone.
  const match = /^(~|\$HOME|\$\{HOME\})(?=$|[/\\])/.exec(value);
  if (!match) return value;
  const rest = value.slice(match[0].length).replace(/^[/\\]+/, "");
  return rest ? join(homedir(), rest) : homedir();
}
