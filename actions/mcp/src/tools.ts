/**
 * The tool surface.
 *
 * Five tools. The names and descriptions here are shown to the person in Claude
 * Desktop when it asks permission to run something, so they are written to be
 * read by someone who has never heard of govbot — and every claim they make is
 * literally true of what the tool does.
 */

import { z } from "zod";
import * as govbot from "./govbot.js";
import * as workspace from "./workspace.js";

/** What a tool hands back: text for the model, plus the structured payload. */
export interface ToolOutput {
  text: string;
  data?: unknown;
  isError?: boolean;
}

const LOOKUP_LINKS = [
  "State legislators and districts: https://openstates.org/find_your_legislator/",
  "Members of Congress: https://www.congress.gov/members/find-your-member",
].join("\n");

// ---------------------------------------------------------------------------
// setup_workspace
// ---------------------------------------------------------------------------

export const setupWorkspaceSchema = {};

export async function setupWorkspace(): Promise<ToolOutput> {
  const result = await workspace.ensure();
  const config = await workspace.readConfig();
  const cli = await govbot.version();

  const lines = [
    result.created
      ? `Created a workspace at ${result.path}`
      : `Workspace is at ${result.path}`,
    "",
    "This folder belongs to the person using it. It holds their govbot.yml, the",
    "legislation cloned so far, and the topic scores. Nothing in it is sent anywhere.",
  ];
  if (result.isGitRepo) {
    lines.push("It is a git repository, so it can be published to GitHub as-is.");
  }
  lines.push(
    "",
    `Jurisdictions tracked: ${config.repos.length ? config.repos.join(", ") : "none yet"}`,
    `Topics defined: ${Object.keys(config.tags).length ? Object.keys(config.tags).join(", ") : "none yet"}`,
    `govbot CLI: ${cli ?? "NOT FOUND — the other tools will not work until it is installed"}`,
  );

  return {
    text: lines.join("\n"),
    data: { ...result, repos: config.repos, tags: Object.keys(config.tags), cli },
  };
}

// ---------------------------------------------------------------------------
// check_local_data
// ---------------------------------------------------------------------------

export const checkLocalDataSchema = {
  jurisdictions: z
    .array(z.string())
    .optional()
    .describe(
      "Jurisdictions to report on, as locale codes (`il`, `usa`) or Open Civic Data ids. Omit for everything already cloned.",
    ),
};

export async function checkLocalData(args: {
  jurisdictions?: string[];
}): Promise<ToolOutput> {
  await workspace.ensure();
  const config = await workspace.readConfig();

  const cli = await govbot.version();
  if (!cli) {
    return {
      isError: true,
      text:
        "The govbot command-line tool is not installed, so there is no local data to read.\n\n" +
        'Install it with:\n  sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"',
    };
  }

  const args_ = ["query", "coverage", "--govbot-dir", workspace.dataPath()];
  for (const jurisdiction of args.jurisdictions ?? []) {
    args_.push("--jurisdiction", jurisdiction);
  }

  let response: QueryResponse;
  try {
    response = await govbot.runJson<QueryResponse>(args_, {
      cwd: workspace.workspacePath(),
    });
  } catch (error) {
    // Nothing cloned yet is the normal first-run state, not a failure.
    return {
      text:
        "No government data has been cloned to this computer yet.\n\n" +
        "Ask which state the person lives in, then use clone_government_data. " +
        "For Congress, clone `usa` as well.\n\n" +
        `Workspace: ${workspace.workspacePath()}\n` +
        (error instanceof govbot.GovbotError && error.detail ? `\n${error.detail}` : ""),
      data: { cloned: [], workspace: workspace.workspacePath() },
    };
  }

  return {
    text: describeCoverage(response, config),
    data: response,
  };
}

// ---------------------------------------------------------------------------
// clone_government_data
// ---------------------------------------------------------------------------

export const cloneSchema = {
  jurisdictions: z
    .array(z.string())
    .min(1)
    .describe(
      "Jurisdictions to clone, as locale codes: two-letter state codes (`il`, `wy`), `usa` for Congress, or `dc`, `pr`, `gu`, `vi`, `mp`.",
    ),
};

export async function clone(
  args: { jurisdictions: string[] },
  onProgress?: (message: string) => void,
): Promise<ToolOutput> {
  await workspace.ensure();

  const locales = args.jurisdictions.map((j) => normalizeLocale(j));
  const result = await govbot.run(
    ["clone", ...locales, "--govbot-dir", workspace.dataPath()],
    {
      cwd: workspace.workspacePath(),
      onProgress: (chunk) => {
        for (const line of chunk.split("\n")) {
          const trimmed = line.trim();
          if (trimmed) onProgress?.(trimmed);
        }
      },
    },
  );

  if (result.code !== 0) {
    return {
      isError: true,
      text:
        `Cloning failed for: ${locales.join(", ")}\n\n` +
        (result.stderr.trim() || `Exit code ${result.code}`),
    };
  }

  await workspace.addRepos(locales);

  return {
    text:
      `Cloned ${locales.join(", ")} into ${workspace.dataPath()}.\n\n` +
      "This is public data from git repositories — no account, no API key, and no\n" +
      "record of the request anywhere but this computer.\n\n" +
      result.stderr.trim(),
    data: { cloned: locales },
  };
}

// ---------------------------------------------------------------------------
// save_my_values
// ---------------------------------------------------------------------------

const tagSchema = z.object({
  name: z
    .string()
    .describe("A short name for the topic, e.g. 'renter protections'."),
  description: z
    .string()
    .describe("What this topic covers. Embedded and compared against every bill."),
  examples: z
    .array(z.string())
    .optional()
    .describe("Two or three sentences describing bills that should match."),
  negative_examples: z
    .array(z.string())
    .optional()
    .describe(
      "Bills on this subject but on the other side of it. This is what turns a subject into a position — include them whenever the person expressed a direction, not just an interest.",
    ),
  include_keywords: z
    .array(z.string())
    .optional()
    .describe(
      "Distinctive terms. Keep this tight: one keyword hit alone lifts a bill to the threshold, so a loose list turns semantic matching into keyword matching.",
    ),
  exclude_keywords: z
    .array(z.string())
    .optional()
    .describe("Terms that disqualify a bill from this topic."),
  threshold: z
    .number()
    .min(0)
    .max(1)
    .optional()
    .describe("Score a bill must reach. Use 0.72; the 0.5 default tags everything."),
});

export const saveValuesSchema = {
  topics: z.array(tagSchema).min(1).describe("The topics to save."),
};

export async function saveValues(args: {
  topics: z.infer<typeof tagSchema>[];
}): Promise<ToolOutput> {
  await workspace.ensure();

  const tags: Record<string, workspace.TagDefinition> = {};
  const warnings: string[] = [];

  for (const topic of args.topics) {
    const { name, ...definition } = topic;
    // Thresholds are not interchangeable. Negative examples subtract roughly 0.17
    // from every score, measured against real bills, so 0.72 with them present is
    // unreachable and the topic silently matches nothing.
    const hasNegatives = Boolean(definition.negative_examples?.length);
    if (definition.threshold === undefined) {
      definition.threshold = hasNegatives ? 0.55 : 0.72;
    } else if (hasNegatives && definition.threshold > 0.6) {
      warnings.push(
        `"${name}" has negative_examples and a threshold of ${definition.threshold}. ` +
          "Negative examples lower every score by roughly 0.17, so this topic would " +
          "match nothing. Lowered it to 0.55.",
      );
      definition.threshold = 0.55;
    }
    if (!definition.include_keywords?.length) {
      warnings.push(
        `"${name}" has no include_keywords. Bill titles are terse enough that the ` +
          "embedding alone barely separates on-topic from off-topic, so this topic " +
          "will match unreliably. Add a few distinctive terms.",
      );
    }
    tags[name] = definition as workspace.TagDefinition;
  }

  const saved = await workspace.saveTags(tags);

  return {
    text: [
      `Saved ${Object.keys(tags).length} topic(s) to ${workspace.configPath()}.`,
      `All topics now defined: ${saved.join(", ")}`,
      "",
      ...(warnings.length ? ["Worth flagging:", ...warnings.map((w) => `  - ${w}`), ""] : []),
      "Run tag_with_local_ai next to score bills against these.",
      "",
      "This file is plain YAML the person can open and edit. Show them what you wrote.",
    ].join("\n"),
    data: { saved, warnings, path: workspace.configPath() },
  };
}

// ---------------------------------------------------------------------------
// tag_with_local_ai
// ---------------------------------------------------------------------------

export const tagSchemaInput = {
  jurisdictions: z
    .array(z.string())
    .optional()
    .describe("Jurisdictions to score. Omit for everything cloned."),
  limit: z
    .number()
    .int()
    .positive()
    .optional()
    .describe(
      "Bills to score per jurisdiction. Scoring runs at roughly 25 bills per second, so keep this in the hundreds for an interactive answer.",
    ),
};

export async function tagWithLocalAi(
  args: { jurisdictions?: string[]; limit?: number },
  onProgress?: (message: string) => void,
): Promise<ToolOutput> {
  await workspace.ensure();

  const config = await workspace.readConfig();
  if (!Object.keys(config.tags).length) {
    return {
      isError: true,
      text:
        "No topics are defined yet, so there is nothing to score against.\n" +
        "Use save_my_values first.",
    };
  }

  const logsArgs = [
    "logs",
    "--govbot-dir",
    workspace.dataPath(),
    "--join",
    "bill",
    "--filter",
    "none",
    "--limit",
    String(args.limit ?? 400),
  ];
  if (args.jurisdictions?.length) {
    logsArgs.push("--repos", args.jurisdictions.map(normalizeLocale).join(","));
  }

  const logs = await govbot.run(logsArgs, { cwd: workspace.workspacePath() });
  if (logs.code !== 0) {
    return {
      isError: true,
      text: `Reading legislation failed.\n\n${logs.stderr.trim()}`,
    };
  }
  if (!logs.stdout.trim()) {
    return {
      isError: true,
      text:
        "No legislation found to score. Clone a jurisdiction first with " +
        "clone_government_data.",
    };
  }

  // `govbot tag` reads govbot.yml from the working directory and writes tag files
  // beside it, which is exactly what the workspace is for.
  const tagged = await govbot.run(["tag", "--overwrite"], {
    cwd: workspace.workspacePath(),
    stdin: logs.stdout,
    onProgress: (chunk) => {
      for (const line of chunk.split("\n")) {
        const trimmed = line.trim();
        if (trimmed) onProgress?.(trimmed);
      }
    },
  });

  if (tagged.code !== 0) {
    return {
      isError: true,
      text: `Tagging failed.\n\n${tagged.stderr.trim()}`,
    };
  }

  const mode = detectTaggingMode(tagged.stderr);
  const matched = tagged.stdout.trim() ? tagged.stdout.trim().split("\n").length : 0;

  const lines = [
    `Scored bills against: ${Object.keys(config.tags).join(", ")}`,
    `${matched} bill records matched at least one topic.`,
    "",
  ];
  if (mode === "keyword") {
    lines.push(
      "IMPORTANT: this ran in keyword-only mode — the local AI model could not be",
      "loaded or downloaded, so bills were matched on keywords alone rather than",
      "meaning. Results will be noticeably worse. Say so when reporting them.",
      "",
    );
  } else {
    lines.push(
      "Scored with a local embedding model running on this computer. No bill text and",
      "no topic definition was sent anywhere.",
      "",
    );
  }
  lines.push("Use `query` with a `tag` to pull the highest-scoring bills.");

  return {
    text: lines.join("\n"),
    data: { mode, matched, topics: Object.keys(config.tags) },
  };
}

/**
 * Which matching mode `govbot tag` actually used.
 *
 * The CLI falls back to keyword matching when the embedding model is missing and
 * says so only on stderr. Passing keyword results off as AI tagging would be a
 * quiet accuracy regression the person cannot see, so it is detected and reported.
 */
export function detectTaggingMode(stderr: string): "embedding" | "keyword" {
  return /keyword-based matching|Embedding files not available/i.test(stderr)
    ? "keyword"
    : "embedding";
}

// ---------------------------------------------------------------------------
// query
// ---------------------------------------------------------------------------

export const querySchema = {
  type: z
    .enum(["bills", "votes", "people", "coverage"])
    .describe(
      "bills: legislation. votes: roll calls. people: the names present in the data. coverage: what the data can and cannot answer.",
    ),
  jurisdictions: z
    .array(z.string())
    .optional()
    .describe(
      "Locale codes (`il`, `usa`) or Open Civic Data ids such as `ocd-jurisdiction/country:us/state:il/government` or `ocd-division/country:us/state:il/sldl:4`. Omit for everything cloned.",
    ),
  person: z
    .string()
    .optional()
    .describe(
      "A legislator's name, matched against sponsors and voters. If it comes back ambiguous, ask which person is meant rather than choosing.",
    ),
  tag: z
    .string()
    .optional()
    .describe("A topic from save_my_values. Ranks and filters results by score."),
  text: z
    .string()
    .optional()
    .describe("Words that must all appear in the bill, matched as whole words."),
  subject: z.string().optional().describe("A subject term the jurisdiction assigned."),
  identifier: z.string().optional().describe("A single bill, e.g. `HB1234`."),
  session: z.string().optional().describe("A single legislative session."),
  min_score: z
    .number()
    .optional()
    .describe("Lowest topic score to include. Defaults to the topic's threshold."),
  min_confidence: z
    .enum(["any", "medium", "high", "exact"])
    .optional()
    .describe(
      "How certain a name match must be before anything is attributed to that person. Defaults to medium.",
    ),
  limit: z.number().int().positive().max(100).optional().describe("Rows to return (default 20)."),
};

interface QueryResponse {
  query: Record<string, unknown>;
  results: Record<string, unknown>[];
  truncation: { returned: number; total_matching: number; limit: number };
  coverage: CoverageEntry[];
  caveats?: string[];
}

interface CoverageEntry {
  jurisdiction: { id: string; name: string | null; locale: string };
  bills: number;
  vote_events: number;
  member_vote_rows: number;
  roll_call_data: "none" | "counts_only" | "available";
  sessions: string[];
}

export async function query(args: Record<string, unknown>): Promise<ToolOutput> {
  await workspace.ensure();

  const cliArgs = ["query", String(args.type), "--govbot-dir", workspace.dataPath()];

  for (const jurisdiction of (args.jurisdictions as string[] | undefined) ?? []) {
    cliArgs.push("--jurisdiction", jurisdiction);
  }
  const passthrough: [string, string][] = [
    ["person", "--person"],
    ["tag", "--tag"],
    ["text", "--text"],
    ["subject", "--subject"],
    ["identifier", "--identifier"],
    ["session", "--session"],
    ["min_confidence", "--min-confidence"],
  ];
  for (const [key, flag] of passthrough) {
    const value = args[key];
    if (value !== undefined && value !== null && value !== "") {
      cliArgs.push(flag, String(value));
    }
  }
  if (typeof args.min_score === "number") cliArgs.push("--min-score", String(args.min_score));
  cliArgs.push("--limit", String(args.limit ?? 20));

  let response: QueryResponse;
  try {
    response = await govbot.runJson<QueryResponse>(cliArgs, {
      cwd: workspace.workspacePath(),
    });
  } catch (error) {
    if (error instanceof govbot.GovbotError) {
      return {
        isError: true,
        text: [error.message, error.detail ?? ""].filter(Boolean).join("\n\n"),
      };
    }
    throw error;
  }

  return { text: summarize(response), data: response };
}

// ---------------------------------------------------------------------------
// Shaping results for the model
// ---------------------------------------------------------------------------

/**
 * A short prose summary in front of the JSON.
 *
 * The point is that the reasons an answer might be incomplete are stated up
 * front rather than buried in a field the model may not read.
 */
function summarize(response: QueryResponse): string {
  const lines: string[] = [];
  const { returned, total_matching, limit } = response.truncation;

  if (returned === 0) {
    lines.push("No matching records.");
  } else if (total_matching > returned) {
    lines.push(`Showing ${returned} of ${total_matching} matches (limit ${limit}).`);
  } else {
    lines.push(`${returned} match${returned === 1 ? "" : "es"}.`);
  }

  for (const entry of response.coverage ?? []) {
    const name = entry.jurisdiction.name ?? entry.jurisdiction.locale.toUpperCase();
    const rollCall =
      entry.roll_call_data === "available"
        ? `${entry.vote_events} recorded votes`
        : entry.roll_call_data === "counts_only"
          ? `${entry.vote_events} vote totals but no individual votes`
          : "NO recorded votes at all";
    lines.push(`  ${name}: ${entry.bills} bills, ${rollCall}.`);
  }

  if (response.caveats?.length) {
    lines.push("", "Read these before answering:");
    for (const caveat of response.caveats) lines.push(`  - ${caveat}`);
  }

  lines.push("", JSON.stringify(response.results, null, 2));
  return lines.join("\n");
}

function describeCoverage(
  response: QueryResponse,
  config: workspace.GovbotConfig,
): string {
  const lines = [`Workspace: ${workspace.workspacePath()}`, ""];

  if (!response.coverage?.length) {
    lines.push(
      "No government data cloned yet. Ask which state the person is in, then use",
      "clone_government_data — and clone `usa` too if they want Congress.",
    );
    return lines.join("\n");
  }

  lines.push("Cloned to this computer:");
  for (const entry of response.coverage) {
    const name = entry.jurisdiction.name ?? entry.jurisdiction.locale.toUpperCase();
    lines.push(
      `  ${name} (${entry.jurisdiction.locale}) — ${entry.bills} bills, ` +
        `${entry.vote_events} vote events, sessions ${entry.sessions.join(", ") || "none"}`,
    );
    if (entry.roll_call_data === "none") {
      lines.push(
        `    No roll-call votes published. Sponsorship is the only evidence here.`,
      );
    } else if (entry.roll_call_data === "counts_only") {
      lines.push(`    Vote totals only — individual votes are not published.`);
    }
  }

  lines.push(
    "",
    `Topics defined: ${Object.keys(config.tags).length ? Object.keys(config.tags).join(", ") : "none yet"}`,
  );
  if (response.caveats?.length) {
    lines.push("", "Read these before answering:");
    for (const caveat of response.caveats) lines.push(`  - ${caveat}`);
  }
  lines.push("", "Finding someone's representatives:", LOOKUP_LINKS);
  return lines.join("\n");
}

/**
 * Accept an OCD id wherever a locale code is expected, since the model is told
 * to speak OCD elsewhere and `clone` only understands locales.
 */
export function normalizeLocale(input: string): string {
  const trimmed = input.trim().toLowerCase();
  const stateMatch = trimmed.match(/\bstate:([a-z]{2,3})\b/);
  if (stateMatch?.[1]) return stateMatch[1];
  if (trimmed.startsWith("ocd-")) return "usa"; // `country:us` with no state is Congress.
  return trimmed;
}
