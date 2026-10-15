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
import { type Document, isMap, isScalar, isSeq, parseDocument, stringify as stringifyYaml } from "yaml";

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
 * Safe to call repeatedly: existing files are left exactly as they are, so a
 * user's edits to `govbot.yml`, `README.md` and `.gitignore` are never
 * overwritten. Only the tools that write (setup, clone, save, tag) call this.
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
  // Written only when missing, the same rule as govbot.yml. The README tells the
  // person the folder is theirs to edit, so a note they add to it (or a line they
  // add to .gitignore) must survive the next tool call.
  await writeIfMissing(join(path, "README.md"), README);
  await writeIfMissing(join(path, ".gitignore"), GITIGNORE);

  const isGitRepo = await ensureGitRepo(path);
  return { path, created: !alreadyExisted, isGitRepo };
}

async function writeIfMissing(file: string, contents: string): Promise<void> {
  if (!existsSync(file)) await writeFile(file, contents, "utf8");
}

/**
 * The working directory for read-only `govbot` commands.
 *
 * Reads must never create the workspace (check_local_data and query are marked
 * read-only), so they cannot simply use the workspace path: before the first
 * setup or clone it does not exist, and spawning a process there fails. Every
 * read passes `--govbot-dir` explicitly, so the home directory is a harmless
 * stand-in; the CLI then reports "nothing cloned" in its own words.
 */
export function readCwd(): string {
  const path = workspacePath();
  return existsSync(path) ? path : homedir();
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

/**
 * `govbot.yml` exists but cannot be safely edited: it does not parse, or its
 * shape is not what this server knows how to update.
 *
 * Thrown instead of falling back to an empty config, because the next save
 * would then write that empty config over every topic the person defined.
 * The message is written for the person, and names the file and the problem.
 */
export class ConfigError extends Error {
  constructor(problem: string) {
    super(
      `Could not update ${configPath()}, so it was left exactly as it was: ${problem}\n\n` +
        "Fix that in the file, or move the file aside to start fresh, then try again. " +
        "Do not recreate the file: the topics the person defined are in it.",
    );
    this.name = "ConfigError";
  }
}

/**
 * Parse `govbot.yml` as an editable document, or return null if there is no file.
 *
 * A missing file means "start fresh". Anything else that goes wrong is thrown:
 * a YAML error (as a ConfigError with line and column), or an unreadable file.
 */
async function loadDocument(): Promise<Document | null> {
  let raw: string;
  try {
    raw = await readFile(configPath(), "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
  const doc = parseDocument(raw);
  const [firstError] = doc.errors;
  if (firstError) {
    // The library's message reads "<what> at line L, column C:" followed by a
    // snippet; the part before the snippet is what a person can act on.
    throw new ConfigError(firstError.message.split(":\n")[0] ?? firstError.message);
  }
  // An empty file, or one holding only comments, has no contents. That is fine;
  // a list or a bare string at the top level is not something we can add keys to.
  if (doc.contents !== null && !isMap(doc.contents)) {
    throw new ConfigError("the top level is not a set of `key: value` entries.");
  }
  return doc;
}

export async function readConfig(): Promise<GovbotConfig> {
  const doc = await loadDocument();
  const parsed = (doc?.toJS() ?? null) as Partial<GovbotConfig> | null;
  return {
    $schema: parsed?.$schema ?? SCHEMA_URL,
    repos: parsed?.repos ?? [],
    tags: parsed?.tags ?? {},
  };
}

/** Write a whole new `govbot.yml`. Only for creating the file; edits go through editConfig. */
export async function writeConfig(config: GovbotConfig): Promise<void> {
  await mkdir(workspacePath(), { recursive: true });
  await writeFile(configPath(), freshConfigText(config), "utf8");
}

function freshConfigText(config: GovbotConfig): string {
  const header =
    "# Your govbot project.\n" +
    "#\n" +
    "# `repos` are the jurisdictions being tracked. `tags` are the topics you care\n" +
    "# about, written so a local AI model can score bills against them. Both are\n" +
    "# yours to edit — this file is read, not owned, by the Claude Desktop extension.\n" +
    "#\n" +
    "# Run `govbot logs | govbot tag` in this folder to re-score bills after editing.\n\n";
  return header + stringifyYaml(config, { lineWidth: 88 });
}

/**
 * Change `govbot.yml` in place, touching only what `edit` touches.
 *
 * The file is edited as a YAML document rather than re-serialised from a plain
 * object, so the person's comments, key order and keys this server does not
 * know about all survive. If the file does not parse, nothing is written.
 */
/**
 * The node under a top-level key, or undefined when the key is absent or has no
 * value (`repos:` on its own line), which the old reader also treated as empty.
 */
function topLevel(doc: Document, key: string): unknown {
  const node = doc.get(key, true);
  if (node == null || (isScalar(node) && node.value == null)) return undefined;
  return node;
}

async function editConfig<T>(edit: (doc: Document) => T): Promise<T> {
  let doc = await loadDocument();
  if (doc === null) {
    doc = parseDocument(freshConfigText({ $schema: SCHEMA_URL, repos: [], tags: {} }));
  }
  if (doc.contents === null) doc.contents = doc.createNode({});
  const result = edit(doc);
  await mkdir(workspacePath(), { recursive: true });
  await writeFile(configPath(), doc.toString({ lineWidth: 88 }), "utf8");
  return result;
}

/**
 * Record the jurisdictions being tracked, preserving any already listed.
 *
 * New entries are appended, in sorted order, after the person's own; the list
 * is not re-sorted, so a comment next to an entry stays next to it.
 */
export async function addRepos(locales: string[]): Promise<string[]> {
  return editConfig((doc) => {
    const node = topLevel(doc, "repos");
    if (node !== undefined && !isSeq(node)) {
      throw new ConfigError("`repos` is not a list, so new jurisdictions cannot be added to it.");
    }
    const existing = (node?.toJSON() ?? []) as unknown[];
    const additions = [...new Set(locales.map((l) => l.toLowerCase()))]
      .filter((l) => !existing.includes(l))
      .sort();
    if (!node || node.items.length === 0) {
      // Absent, or the `repos: []` of a fresh file: write a block list rather
      // than growing the inline `[]` into `[ il, usa ]`.
      doc.set("repos", doc.createNode(additions));
    } else {
      for (const locale of additions) node.add(locale);
    }
    return [...existing.map(String), ...additions];
  });
}

/**
 * Save topic definitions, replacing any with the same name.
 *
 * `govbot tag` keys its cached scores on a hash of the tag definition, so
 * changing a definition here correctly invalidates the previous scores.
 * Other topics, and comments around them, are left as they are.
 */
export async function saveTags(tags: Record<string, TagDefinition>): Promise<string[]> {
  return editConfig((doc) => {
    const node = topLevel(doc, "tags");
    if (node !== undefined && !isMap(node)) {
      throw new ConfigError("`tags` is not a set of named topics, so topics cannot be added to it.");
    }
    // A fresh file has `tags: {}`; let it become a normal block mapping.
    if (node === undefined) doc.set("tags", doc.createNode({}));
    else if (node.items.length === 0) node.flow = false;
    for (const [name, definition] of Object.entries(tags)) {
      doc.setIn(["tags", name], doc.createNode(definition));
    }
    const all = doc.get("tags", true);
    return Object.keys(isMap(all) ? (all.toJSON() as object) : {}).sort();
  });
}
