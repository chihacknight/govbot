/**
 * The workspace: a real folder on the user's computer that they own.
 *
 * Everything this server does happens inside one directory — the cloned data,
 * the `govbot.yml` describing what the user cares about, and the tag output.
 * It is a git repository from the moment it is created, so "publish this to
 * GitHub" is a real next step rather than a promise.
 *
 * The workspace also resolves a constraint rather than fighting it. `govbot
 * tag` requires `govbot.yml` in the *current working directory* and writes its
 * output relative to that directory, and `govbot logs --join tags` looks for
 * tags relative to the current directory too. A server with one fixed
 * workspace directory satisfies all of that by construction.
 */

import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { parse as parseYaml, stringify as stringifyYaml } from "yaml";

const execFileAsync = promisify(execFile);

/** A topic definition, in the shape `govbot.yml` expects. */
export interface TagDefinition {
  description: string;
  examples?: string[];
  negative_examples?: string[];
  include_keywords?: string[];
  exclude_keywords?: string[];
  threshold?: number;
}

export interface GovbotConfig {
  $schema?: string;
  repos: string[];
  tags: Record<string, TagDefinition>;
  [key: string]: unknown;
}

const SCHEMA_URL =
  "https://raw.githubusercontent.com/chihacknight/govbot/main/schemas/govbot.schema.json";

/** Where the workspace lives. */
export function workspacePath(): string {
  return process.env.GOVBOT_WORKSPACE ?? join(homedir(), "govbot-workspace");
}

/** Where `govbot clone` puts repositories, inside the workspace. */
export function dataPath(): string {
  return join(workspacePath(), "govbot_data");
}

export function configPath(): string {
  return join(workspacePath(), "govbot.yml");
}

export function exists(): boolean {
  return existsSync(configPath());
}

const README = `# My govbot workspace

This folder was created by the govbot extension for Claude Desktop. **It belongs to
you.** Nothing in it is sent anywhere, and you can read, edit, delete, or publish
any of it.

## What is in here

- **govbot.yml** — the jurisdictions being tracked, and the topics you said you
  care about, written as definitions a local AI model can match bills against.
  This is the interesting file. Open it and see whether it describes what you
  actually meant; if it doesn't, edit it.
- **govbot_data/** — legislation cloned from public git repositories, one per
  jurisdiction. Not committed, because it is large and it is already public.
- **country:us/** — topic scores, one file per topic per session, written by the
  local tagging model.

## Running it yourself

Everything Claude does here, you can do from a terminal in this folder:

    govbot clone il usa      # fetch jurisdictions
    govbot logs | govbot tag # score bills against the topics in govbot.yml
    govbot query bills --tag "renter protections" --limit 20
    govbot query coverage    # what the data can and cannot answer

## Publishing

This folder is a git repository. To share it:

    git add -A
    git commit -m "my legislative interests"
    gh repo create my-govbot --public --source=. --push

The cloned data is excluded, so what you publish is your configuration and your
topic scores — not a copy of the whole corpus.
`;

const GITIGNORE = `# Cloned legislation: large, and already public elsewhere.
govbot_data/

# The local embedding model.
model.onnx
tokenizer.json
vocab.txt
`;

/**
 * Create the workspace if it is not already there, and return what happened.
 *
 * Safe to call repeatedly: an existing workspace is left exactly as it is, so a
 * user's edits to `govbot.yml` are never overwritten.
 */
export async function ensure(): Promise<{
  path: string;
  created: boolean;
  isGitRepo: boolean;
}> {
  const path = workspacePath();
  const alreadyExisted = exists();

  await mkdir(path, { recursive: true });
  await mkdir(dataPath(), { recursive: true });

  if (!alreadyExisted) {
    await writeConfig({ $schema: SCHEMA_URL, repos: [], tags: {} });
  }
  // These two are safe to refresh — neither is something a user edits.
  await writeFile(join(path, "README.md"), README, "utf8");
  await writeFile(join(path, ".gitignore"), GITIGNORE, "utf8");

  const isGitRepo = await ensureGitRepo(path);
  return { path, created: !alreadyExisted, isGitRepo };
}

/**
 * Make the workspace a git repository, so the user can publish it.
 *
 * Failure is not fatal — git may not be installed, and the workspace is still
 * perfectly usable without it.
 */
async function ensureGitRepo(path: string): Promise<boolean> {
  if (existsSync(join(path, ".git"))) return true;
  try {
    await execFileAsync("git", ["init", "--quiet"], { cwd: path });
    return true;
  } catch {
    return false;
  }
}

export async function readConfig(): Promise<GovbotConfig> {
  try {
    const raw = await readFile(configPath(), "utf8");
    const parsed = parseYaml(raw) as Partial<GovbotConfig> | null;
    return {
      $schema: parsed?.$schema ?? SCHEMA_URL,
      repos: parsed?.repos ?? [],
      tags: parsed?.tags ?? {},
    };
  } catch {
    return { $schema: SCHEMA_URL, repos: [], tags: {} };
  }
}

export async function writeConfig(config: GovbotConfig): Promise<void> {
  await mkdir(workspacePath(), { recursive: true });
  const header =
    "# Your govbot project.\n" +
    "#\n" +
    "# `repos` are the jurisdictions being tracked. `tags` are the topics you care\n" +
    "# about, written so a local AI model can score bills against them. Both are\n" +
    "# yours to edit — this file is read, not owned, by the Claude Desktop extension.\n" +
    "#\n" +
    "# Run `govbot logs | govbot tag` in this folder to re-score bills after editing.\n\n";
  await writeFile(configPath(), header + stringifyYaml(config, { lineWidth: 88 }), "utf8");
}

/**
 * Record the jurisdictions being tracked, preserving any already listed.
 */
export async function addRepos(locales: string[]): Promise<string[]> {
  const config = await readConfig();
  const merged = new Set([...config.repos, ...locales.map((l) => l.toLowerCase())]);
  config.repos = [...merged].sort();
  await writeConfig(config);
  return config.repos;
}

/**
 * Save topic definitions, replacing any with the same name.
 *
 * `govbot tag` keys its cached scores on a hash of the tag definition, so
 * changing a definition here correctly invalidates the previous scores.
 */
export async function saveTags(tags: Record<string, TagDefinition>): Promise<string[]> {
  const config = await readConfig();
  config.tags = { ...config.tags, ...tags };
  await writeConfig(config);
  return Object.keys(config.tags).sort();
}
