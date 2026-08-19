#!/usr/bin/env node
/**
 * govbot for Claude Desktop.
 *
 * A thin adapter over the `govbot` command-line tool. It owns no data model and
 * no index; everything it reports comes from the CLI, so a person can reproduce
 * any answer from a terminal in the same workspace folder.
 *
 * Stdout belongs to the MCP transport. Nothing in this process may print to it.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { readFile } from "node:fs/promises";
import { z } from "zod";

import { SERVER_INSTRUCTIONS } from "./instructions.js";
import * as tools from "./tools.js";
import * as workspace from "./workspace.js";

const VERSION = "0.1.0";

/** Diagnostics go to stderr. Writing to stdout would corrupt the transport. */
function log(message: string): void {
  process.stderr.write(`[govbot-mcp] ${message}\n`);
}

const server = new McpServer(
  { name: "govbot", version: VERSION },
  { instructions: SERVER_INSTRUCTIONS },
);

/** Turn a tool result into MCP content, and never throw out of a handler. */
function respond(output: tools.ToolOutput) {
  return {
    content: [{ type: "text" as const, text: output.text }],
    ...(output.isError ? { isError: true } : {}),
  };
}

function failure(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  log(`tool error: ${message}`);
  return {
    content: [{ type: "text" as const, text: message }],
    isError: true,
  };
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

server.registerTool(
  "setup_workspace",
  {
    title: "Create your legislation workspace",
    description:
      "Create a folder on this computer for tracking legislation. You own it — it holds " +
      "the data cloned so far and a plain-text file describing the topics you care about, " +
      "and it can be published to GitHub or deleted at any time.",
    inputSchema: tools.setupWorkspaceSchema,
  },
  async () => {
    try {
      return respond(await tools.setupWorkspace());
    } catch (error) {
      return failure(error);
    }
  },
);

server.registerTool(
  "check_local_data",
  {
    title: "See what data is on this computer",
    description:
      "Report which jurisdictions have been cloned, how many bills and recorded votes " +
      "each has, and what questions that data can and cannot answer.",
    inputSchema: tools.checkLocalDataSchema,
  },
  async (args) => {
    try {
      return respond(await tools.checkLocalData(args));
    } catch (error) {
      return failure(error);
    }
  },
);

server.registerTool(
  "clone_government_data",
  {
    title: "Privately clone government data",
    description:
      "Download legislation for one or more jurisdictions from public git repositories " +
      "to this computer. No account, no API key, and no record of what you look up — " +
      "every later question is answered from the local copy.",
    inputSchema: tools.cloneSchema,
  },
  async (args, extra) => {
    try {
      return respond(
        await tools.clone(args, (message) => {
          extra.sendNotification?.({
            method: "notifications/message",
            params: { level: "info", data: message },
          }).catch(() => {
            // Progress is best-effort; a client that does not accept it is fine.
          });
        }),
      );
    } catch (error) {
      return failure(error);
    }
  },
);

server.registerTool(
  "save_my_values",
  {
    title: "Save what you care about",
    description:
      "Write the topics you care about into your workspace as reusable definitions. " +
      "They are saved as plain YAML you can read, edit, and re-run yourself.",
    inputSchema: tools.saveValuesSchema,
  },
  async (args) => {
    try {
      return respond(await tools.saveValues(args));
    } catch (error) {
      return failure(error);
    }
  },
);

server.registerTool(
  "tag_with_local_ai",
  {
    title: "Tag legislation with a local AI model",
    description:
      "Score bills against your saved topics using an AI model that runs on this " +
      "computer. Your topics and the bill text never leave the machine, and there is " +
      "no per-use cost.",
    inputSchema: tools.tagSchemaInput,
  },
  async (args, extra) => {
    try {
      return respond(
        await tools.tagWithLocalAi(args, (message) => {
          extra.sendNotification?.({
            method: "notifications/message",
            params: { level: "info", data: message },
          }).catch(() => {});
        }),
      );
    } catch (error) {
      return failure(error);
    }
  },
);

server.registerTool(
  "query",
  {
    title: "Search cloned legislation",
    description:
      "Search the legislation on this computer: bills, roll-call votes, the people " +
      "named in the data, or a report of what the data covers. Every result carries the " +
      "repository, commit, and file path it came from.",
    inputSchema: tools.querySchema,
  },
  async (args) => {
    try {
      return respond(await tools.query(args));
    } catch (error) {
      return failure(error);
    }
  },
);

// ---------------------------------------------------------------------------
// Resources — the workspace, so a person can inspect what was decided for them
// ---------------------------------------------------------------------------

server.registerResource(
  "values",
  "govbot://workspace/govbot.yml",
  {
    title: "Your saved values",
    description:
      "The topics recorded as yours, and the jurisdictions being tracked. Open this to " +
      "check whether it describes what you actually meant.",
    mimeType: "application/yaml",
  },
  async (uri) => {
    const text = await readFile(workspace.configPath(), "utf8").catch(
      () => "# No workspace yet. Ask Claude to set one up.\n",
    );
    return { contents: [{ uri: uri.href, mimeType: "application/yaml", text }] };
  },
);

server.registerResource(
  "readme",
  "govbot://workspace/README.md",
  {
    title: "About your workspace",
    description: "What this folder is, how to run it yourself, and how to publish it.",
    mimeType: "text/markdown",
  },
  async (uri) => {
    const text = await readFile(
      `${workspace.workspacePath()}/README.md`,
      "utf8",
    ).catch(() => "# No workspace yet. Ask Claude to set one up.\n");
    return { contents: [{ uri: uri.href, mimeType: "text/markdown", text }] };
  },
);

server.registerResource(
  "coverage",
  "govbot://workspace/coverage",
  {
    title: "What your local data covers",
    description:
      "Which jurisdictions are cloned, how much legislation each has, and whether it " +
      "publishes individual votes.",
    mimeType: "text/plain",
  },
  async (uri) => {
    const output = await tools.checkLocalData({});
    return { contents: [{ uri: uri.href, mimeType: "text/plain", text: output.text }] };
  },
);

// ---------------------------------------------------------------------------
// Prompt — so the flow is one click for someone who does not know what to type
// ---------------------------------------------------------------------------

server.registerPrompt(
  "who_are_my_reps",
  {
    title: "Who represents me, and how do they vote?",
    description:
      "Walk through finding your representatives and comparing their record against " +
      "what you care about.",
    argsSchema: {
      state: z
        .string()
        .optional()
        .describe("Your state, e.g. Illinois — optional, Claude will ask if omitted."),
      values: z
        .string()
        .optional()
        .describe("What you care about, in your own words — optional."),
    },
  },
  ({ state, values }) => ({
    messages: [
      {
        role: "user" as const,
        content: {
          type: "text" as const,
          text: [
            "I want to know who represents me and how their record lines up with what I care about.",
            state ? `I live in ${state}.` : "",
            values ? `What I care about: ${values}` : "",
            "",
            "Please start by checking what data is already on this computer, then ask me for",
            "anything you need. Don't ask for my address — point me at a lookup site instead.",
            "Tell me plainly where the data can't answer a question rather than guessing.",
          ]
            .filter(Boolean)
            .join("\n"),
        },
      },
    ],
  }),
);

// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log(`ready (v${VERSION}, workspace ${workspace.workspacePath()})`);
}

main().catch((error) => {
  log(`fatal: ${error instanceof Error ? error.stack : String(error)}`);
  process.exit(1);
});
